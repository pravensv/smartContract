// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UniversalEscrowRules
 * @dev Multi-party Escrow Smart Contract with comprehensive rules for all API lifecycle stages:
 *      Create, Buy (Fund), Delivery, 5-Day Return Window Hold, Merchant Release, Buyer Refund, and Arbiter Dispute Resolution.
 *
 * KEY RULE ENFORCEMENT:
 * 1. Creation Rule: Valid addresses for Buyer, Seller, Arbiter; amount > 0; Buyer != Seller. Default 5-day return period.
 * 2. Funding Rule: Only designated Buyer can deposit exact amount in CREATED state.
 * 3. Delivery Rule: Product marked as delivered records timestamp and starts the 5-day return period countdown.
 * 4. Return Window Hold Rule: During the 5 days post-delivery, funds remain held in vault. Buyer can trigger return.
 *    Merchant CANNOT release funds during the return window without explicit Buyer early acceptance.
 * 5. Merchant Release Rule: Funds are released to Seller ONLY after the 5-day return period expires without dispute,
 *    or if Buyer explicitly approves early release, or if Arbiter resolves in Seller's favor.
 * 6. Refund Rule: Seller or Arbiter can trigger a full refund to Buyer during Funded/Delivered/Held/Disputed states.
 * 7. Reentrancy Protection: All value-transferring calls are protected with a non-reentrant mutex.
 */
contract UniversalEscrowRules {

    // --- Escrow Lifecycle States ---
    enum EscrowStatus {
        Created,    // 0: Initialized, awaiting funding from buyer
        Funded,     // 1: Buyer deposited funds into vault
        Delivered,  // 2: Product delivered, 5-day return period countdown active
        Held,       // 3: Funds locked/frozen on hold during return request or inspection
        Released,   // 4: Money released to Merchant/Seller after 5 days or early approval
        Refunded,   // 5: Money returned to Buyer after product return or cancellation
        Disputed    // 6: Formal dispute raised, awaiting Arbiter resolution
    }

    // --- Immutable Agreement Terms ---
    address payable public immutable buyer;
    address payable public immutable seller;
    address public immutable arbiter;
    uint256 public immutable amount;
    string public title;
    
    // --- Return Period Settings ---
    uint256 public constant DEFAULT_RETURN_PERIOD = 60 seconds; // 60 seconds for quick testing & demos
    uint256 public returnPeriodDuration; // Configurable return window duration in seconds
    uint256 public deliveredAt;           // Timestamp when product delivery was confirmed
    string public deliveryTrackingInfo;   // Carrier/tracking reference for product delivery

    // --- Mutable State Variables ---
    EscrowStatus public status;
    string public holdReason;
    uint256 public createdAt;
    uint256 public updatedAt;

    // --- Reentrancy Lock ---
    uint256 private _locked = 1;

    // --- Event Logs ---
    event EscrowCreated(
        address indexed buyer,
        address indexed seller,
        address indexed arbiter,
        uint256 amount,
        uint256 returnPeriodDuration,
        string title
    );
    event BuyFunded(address indexed buyer, uint256 amount, uint256 timestamp);
    event ProductDelivered(address indexed actor, string trackingInfo, uint256 deliveredAt, uint256 returnWindowExpiresAt);
    event ReturnRequested(address indexed buyer, string reason, uint256 timestamp);
    event HoldLocked(address indexed requestedBy, string reason, uint256 timestamp);
    event SellReleased(address indexed requestedBy, address indexed seller, uint256 amount, string notes);
    event RefundedToBuyer(address indexed requestedBy, address indexed buyer, uint256 amount, string reason);
    event DisputeResolved(address indexed arbiter, uint256 sellerAmount, uint256 buyerAmount, string resolutionNotes);

    // --- Access Control Modifiers ---
    modifier onlyBuyer() {
        require(msg.sender == buyer, "Rule Violation: Only designated buyer can execute this");
        _;
    }

    modifier onlySeller() {
        require(msg.sender == seller, "Rule Violation: Only seller can execute this");
        _;
    }

    modifier onlyArbiter() {
        require(msg.sender == arbiter, "Rule Violation: Only arbiter can execute this");
        _;
    }

    modifier onlyAuthorizedActor() {
        require(
            msg.sender == buyer || msg.sender == seller || msg.sender == arbiter,
            "Rule Violation: Only buyer, seller, or arbiter can execute this"
        );
        _;
    }

    modifier onlySellerOrArbiter() {
        require(
            msg.sender == seller || msg.sender == arbiter,
            "Rule Violation: Only seller or arbiter can authorize refund"
        );
        _;
    }

    modifier inState(EscrowStatus expectedState) {
        require(status == expectedState, "Rule Violation: Invalid state for operation");
        _;
    }

    modifier nonReentrant() {
        require(_locked == 1, "ReentrancyGuard: Reentrant call detected");
        _locked = 2;
        _;
        _locked = 1;
    }

    /**
     * @notice RULE 1: Constructor initializes Escrow parameters & 5-day return rule.
     * @param _seller Address of Merchant/Seller.
     * @param _arbiter Address of neutral dispute Arbiter.
     * @param _amount Agreed escrow amount in Wei.
     * @param _title Title of purchase agreement.
     * @param _customReturnPeriodSec Optional custom return period in seconds (0 defaults to 5 days).
     */
    constructor(
        address payable _seller,
        address _arbiter,
        uint256 _amount,
        string memory _title,
        uint256 _customReturnPeriodSec
    ) payable {
        require(_seller != address(0), "Rule Violation: Seller address cannot be zero");
        require(_arbiter != address(0), "Rule Violation: Arbiter address cannot be zero");
        require(msg.sender != _seller, "Rule Violation: Buyer and Seller cannot be the same address");
        require(_amount > 0, "Rule Violation: Escrow amount must be greater than zero");

        buyer = payable(msg.sender);
        seller = _seller;
        arbiter = _arbiter;
        amount = _amount;
        title = _title;

        // Default to 5 days return period if 0 provided
        returnPeriodDuration = _customReturnPeriodSec > 0 ? _customReturnPeriodSec : DEFAULT_RETURN_PERIOD;

        status = EscrowStatus.Created;
        createdAt = block.timestamp;
        updatedAt = block.timestamp;

        emit EscrowCreated(msg.sender, _seller, _arbiter, _amount, returnPeriodDuration, _title);
    }

    /**
     * @notice RULE 2: Buy / Fund Escrow.
     * State Requirement: CREATED
     * Actor Requirement: Buyer ONLY
     * Payment Requirement: msg.value MUST equal exact amount.
     */
    function buy() external payable onlyBuyer inState(EscrowStatus.Created) nonReentrant {
        require(msg.value == amount, "Rule Violation: Deposit must equal exact agreed escrow amount");

        status = EscrowStatus.Funded;
        updatedAt = block.timestamp;

        emit BuyFunded(msg.sender, msg.value, block.timestamp);
    }

    /**
     * @notice RULE 3: Mark Product as Delivered & Start 5-Day Return Window.
     * State Requirement: FUNDED
     * Actor Requirement: Seller, Buyer, or Arbiter
     * @param trackingInfo Delivery tracking reference or courier notes.
     */
    function markDelivered(string calldata trackingInfo) external onlyAuthorizedActor inState(EscrowStatus.Funded) {
        status = EscrowStatus.Delivered;
        deliveredAt = block.timestamp;
        deliveryTrackingInfo = trackingInfo;
        updatedAt = block.timestamp;

        emit ProductDelivered(msg.sender, trackingInfo, deliveredAt, deliveredAt + returnPeriodDuration);
    }

    /**
     * @notice RULE 4: Buyer Return Request (within 5-day return window).
     * State Requirement: DELIVERED
     * Actor Requirement: Buyer ONLY
     * Time Window Requirement: block.timestamp <= deliveredAt + returnPeriodDuration (5 days)
     * @param reason Reason for requesting product return / refund.
     */
    function requestReturn(string calldata reason) external onlyBuyer inState(EscrowStatus.Delivered) {
        require(
            block.timestamp <= deliveredAt + returnPeriodDuration,
            "Rule Violation: 5-day return window has expired"
        );
        require(bytes(reason).length > 0, "Rule Violation: Return reason cannot be empty");

        status = EscrowStatus.Held;
        holdReason = reason;
        updatedAt = block.timestamp;

        emit ReturnRequested(msg.sender, reason, block.timestamp);
    }

    /**
     * @notice RULE 5: Hold / Freeze Escrow.
     * State Requirement: CREATED, FUNDED, or DELIVERED
     * Actor Requirement: Buyer, Seller, or Arbiter
     * @param reason Mandatory reason for putting funds on hold.
     */
    function hold(string calldata reason) external onlyAuthorizedActor {
        require(
            status == EscrowStatus.Created || status == EscrowStatus.Funded || status == EscrowStatus.Delivered,
            "Rule Violation: Cannot put escrow on hold from current state"
        );
        require(bytes(reason).length > 0, "Rule Violation: Hold reason cannot be empty");

        status = EscrowStatus.Held;
        holdReason = reason;
        updatedAt = block.timestamp;

        emit HoldLocked(msg.sender, reason, block.timestamp);
    }

    /**
     * @notice RULE 6: Buyer Early Acceptance.
     * Buyer waives remaining 5-day return period and approves immediate money release to Merchant.
     * State Requirement: DELIVERED
     * Actor Requirement: Buyer ONLY
     * @param settlementNotes Optional notes approving early release.
     */
    function acceptDeliveryEarly(string calldata settlementNotes) external onlyBuyer inState(EscrowStatus.Delivered) nonReentrant {
        _executeReleaseToSeller(msg.sender, settlementNotes);
    }

    /**
     * @notice RULE 7 & 8: Sell / Release Money to Merchant/Seller.
     * Rules Governing Merchant Release:
     * - IF status is DELIVERED: Seller can release ONLY IF 5 days return period has passed (block.timestamp >= deliveredAt + returnPeriodDuration).
     * - IF caller is BUYER: Buyer can approve release at any time during FUNDED or DELIVERED.
     * - IF status is HELD: ONLY Arbiter or Buyer can authorize release.
     * @param settlementNotes Optional settlement details.
     */
    function sell(string calldata settlementNotes) external onlyAuthorizedActor nonReentrant {
        if (status == EscrowStatus.Delivered) {
            if (msg.sender == seller) {
                require(
                    block.timestamp >= deliveredAt + returnPeriodDuration,
                    "Rule Violation: Money is held in 5-day return window. Merchant cannot claim until return period expires or buyer approves early."
                );
            }
        } else if (status == EscrowStatus.Funded) {
            // If not marked delivered yet, buyer or arbiter must approve, or seller if auto-delivery confirmed
            require(
                msg.sender == buyer || msg.sender == arbiter,
                "Rule Violation: Buyer must approve release or product must be marked delivered first"
            );
        } else if (status == EscrowStatus.Held) {
            require(
                msg.sender == buyer || msg.sender == arbiter,
                "Rule Violation: Cannot release held funds without Buyer or Arbiter authorization"
            );
        } else {
            revert("Rule Violation: Invalid state for money release");
        }

        _executeReleaseToSeller(msg.sender, settlementNotes);
    }

    /**
     * @notice RULE 8 (Auto-Release): Merchant claims funds after 5-day return period expires.
     * State Requirement: DELIVERED
     * Time Window Requirement: block.timestamp >= deliveredAt + returnPeriodDuration
     */
    function claimMerchantRelease() external nonReentrant {
        require(status == EscrowStatus.Delivered, "Rule Violation: Escrow must be in DELIVERED state");
        require(
            block.timestamp >= deliveredAt + returnPeriodDuration,
            "Rule Violation: 5-day return window is still active. Funds remain on hold."
        );

        _executeReleaseToSeller(seller, "5-day return period elapsed without dispute. Auto-released to merchant.");
    }

    /**
     * @notice RULE 9: Refund Buyer.
     * Returns vault balance back to Buyer.
     * State Requirement: FUNDED, DELIVERED, HELD, or DISPUTED
     * Actor Requirement: Seller or Arbiter ONLY (Buyer cannot self-refund)
     * @param reason Mandatory reason for executing refund.
     */
    function refund(string calldata reason) external onlySellerOrArbiter nonReentrant {
        require(
            status == EscrowStatus.Funded || status == EscrowStatus.Delivered || status == EscrowStatus.Held || status == EscrowStatus.Disputed,
            "Rule Violation: Cannot refund buyer from current state"
        );
        uint256 vaultBalance = address(this).balance;
        require(vaultBalance >= amount, "Rule Violation: Insufficient vault balance");

        status = EscrowStatus.Refunded;
        holdReason = "";
        updatedAt = block.timestamp;

        (bool success, ) = buyer.call{value: vaultBalance}("");
        require(success, "Rule Violation: Transfer to buyer failed");

        emit RefundedToBuyer(msg.sender, buyer, vaultBalance, reason);
    }

    /**
     * @notice RULE 10: Arbiter Dispute Resolution.
     * Allows neutral Arbiter to resolve disputes by splitting or allocating funds.
     * State Requirement: HELD or DISPUTED
     * Actor Requirement: Arbiter ONLY
     * @param sellerAmount Amount awarded to Seller in Wei.
     * @param buyerAmount Amount awarded to Buyer in Wei.
     * @param resolutionNotes Details of arbiter decision.
     */
    function resolveDispute(
        uint256 sellerAmount,
        uint256 buyerAmount,
        string calldata resolutionNotes
    ) external onlyArbiter nonReentrant {
        require(status == EscrowStatus.Held || status == EscrowStatus.Disputed, "Rule Violation: Contract is not under dispute");
        uint256 vaultBalance = address(this).balance;
        require(sellerAmount + buyerAmount == vaultBalance, "Rule Violation: Split amounts must equal total vault balance");

        status = EscrowStatus.Released;
        holdReason = "";
        updatedAt = block.timestamp;

        if (sellerAmount > 0) {
            (bool successSeller, ) = seller.call{value: sellerAmount}("");
            require(successSeller, "Rule Violation: Transfer to seller failed");
        }
        if (buyerAmount > 0) {
            (bool successBuyer, ) = buyer.call{value: buyerAmount}("");
            require(successBuyer, "Rule Violation: Transfer to buyer failed");
        }

        emit DisputeResolved(msg.sender, sellerAmount, buyerAmount, resolutionNotes);
    }

    /**
     * @dev Internal helper function to execute payout to Seller.
     */
    function _executeReleaseToSeller(address requestedBy, string memory settlementNotes) internal {
        uint256 vaultBalance = address(this).balance;
        require(vaultBalance >= amount, "Rule Violation: Insufficient vault balance for release");

        status = EscrowStatus.Released;
        holdReason = "";
        updatedAt = block.timestamp;

        (bool success, ) = seller.call{value: vaultBalance}("");
        require(success, "Rule Violation: Transfer to seller failed");

        emit SellReleased(requestedBy, seller, vaultBalance, settlementNotes);
    }

    /**
     * @notice RULE 11: Get 5-Day Return Window Status & Timers.
     * @return _isDelivered True if product has been delivered.
     * @return _deliveredAt Timestamp of delivery.
     * @return _returnPeriodSec Duration of return window in seconds (default 5 days = 432,000s).
     * @return _returnWindowExpiresAt Timestamp when return window expires.
     * @return _secondsRemaining Seconds remaining in return window (0 if expired or not delivered).
     * @return _merchantCanClaim True if merchant can claim funds without buyer approval.
     * @return _buyerCanReturn True if buyer is within return period to initiate return.
     */
    function getReturnWindowStatus()
        external
        view
        returns (
            bool _isDelivered,
            uint256 _deliveredAt,
            uint256 _returnPeriodSec,
            uint256 _returnWindowExpiresAt,
            uint256 _secondsRemaining,
            bool _merchantCanClaim,
            bool _buyerCanReturn
        )
    {
        _isDelivered = (status == EscrowStatus.Delivered);
        _deliveredAt = deliveredAt;
        _returnPeriodSec = returnPeriodDuration;
        
        if (_isDelivered) {
            _returnWindowExpiresAt = deliveredAt + returnPeriodDuration;
            if (block.timestamp < _returnWindowExpiresAt) {
                _secondsRemaining = _returnWindowExpiresAt - block.timestamp;
                _merchantCanClaim = false;
                _buyerCanReturn = true;
            } else {
                _secondsRemaining = 0;
                _merchantCanClaim = true;
                _buyerCanReturn = false;
            }
        } else {
            _returnWindowExpiresAt = 0;
            _secondsRemaining = 0;
            _merchantCanClaim = false;
            _buyerCanReturn = false;
        }
    }

    /**
     * @notice Get comprehensive state details of the Escrow agreement.
     */
    function getEscrowDetails()
        external
        view
        returns (
            address _buyer,
            address _seller,
            address _arbiter,
            uint256 _amount,
            uint256 _vaultBalance,
            EscrowStatus _status,
            string memory _title,
            string memory _holdReason,
            uint256 _returnPeriodDuration,
            uint256 _deliveredAt,
            uint256 _createdAt,
            uint256 _updatedAt
        )
    {
        return (
            buyer,
            seller,
            arbiter,
            amount,
            address(this).balance,
            status,
            title,
            holdReason,
            returnPeriodDuration,
            deliveredAt,
            createdAt,
            updatedAt
        );
    }
}
