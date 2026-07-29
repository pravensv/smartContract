// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UniversalEscrow
 * @dev Multi-party Escrow Smart Contract matching the Google Cloud Universal Ledger Escrow API lifecycle.
 *      Enforces strict rules for all operations: Create, Buy (Fund), Delivery, 5-Day Return Window, Hold, Sell, and Refund.
 */
contract UniversalEscrow {
    
    // --- State Enum ---
    enum EscrowStatus {
        Created,    // 0: Initialized, awaiting funding
        Funded,     // 1: Buyer deposited funds into vault
        Delivered,  // 2: Product delivered, 5-day return window active
        Held,       // 3: Locked during inspection, return request, or dispute
        Released,   // 4: Funds settled and sent to Seller after return period or approval
        Refunded,   // 5: Funds returned to Buyer
        Disputed    // 6: Formal dispute flagged by parties
    }

    // --- State Variables ---
    address payable public immutable buyer;
    address payable public immutable seller;
    address public immutable arbiter;
    uint256 public immutable amount;
    string public title;

    // --- Return Window Rule Variables ---
    uint256 public constant DEFAULT_RETURN_PERIOD = 5 days; // 5 days (432,000 seconds)
    uint256 public returnPeriodDuration;                   // Configurable return period
    uint256 public deliveredAt;                             // Product delivery timestamp
    string public deliveryTrackingInfo;                     // Delivery tracking reference

    EscrowStatus public status;
    string public holdReason;
    uint256 public createdAt;
    uint256 public updatedAt;

    // --- Reentrancy Lock ---
    uint256 private _locked = 1;

    // --- Events ---
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
    event DisputeResolved(address indexed arbiter, uint256 sellerAmount, uint256 buyerAmount, string notes);

    // --- Modifiers ---
    modifier onlyBuyer() {
        require(msg.sender == buyer, "Escrow: Only designated buyer can call this");
        _;
    }

    modifier onlyAuthorizedActor() {
        require(
            msg.sender == buyer || msg.sender == seller || msg.sender == arbiter,
            "Escrow: Only buyer, seller, or arbiter can call this"
        );
        _;
    }

    modifier onlySellerOrArbiter() {
        require(
            msg.sender == seller || msg.sender == arbiter,
            "Escrow: Only seller or arbiter can refund buyer"
        );
        _;
    }

    modifier inState(EscrowStatus expectedState) {
        require(status == expectedState, "Escrow: Invalid prerequisite state");
        _;
    }

    modifier nonReentrant() {
        require(_locked == 1, "ReentrancyGuard: reentrant call");
        _locked = 2;
        _;
        _locked = 1;
    }

    /**
     * @notice Constructor initializes the Escrow parameters and sets initial state to Created.
     * @param _seller Address of the Seller (funds recipient upon sale completion).
     * @param _arbiter Address of the independent Arbiter for dispute resolution.
     * @param _amount Required escrow deposit amount in Wei.
     * @param _title Descriptive title or item reference for the agreement.
     */
    constructor(
        address payable _seller,
        address _arbiter,
        uint256 _amount,
        string memory _title
    ) payable {
        require(_seller != address(0), "Escrow: Seller address cannot be zero");
        require(_arbiter != address(0), "Escrow: Arbiter address cannot be zero");
        require(msg.sender != _seller, "Escrow: Buyer and Seller cannot be the same address");
        require(_amount > 0, "Escrow: Amount must be greater than zero");

        buyer = payable(msg.sender);
        seller = _seller;
        arbiter = _arbiter;
        amount = _amount;
        title = _title;
        returnPeriodDuration = DEFAULT_RETURN_PERIOD; // 5 days

        status = EscrowStatus.Created;
        createdAt = block.timestamp;
        updatedAt = block.timestamp;

        emit EscrowCreated(msg.sender, _seller, _arbiter, _amount, DEFAULT_RETURN_PERIOD, _title);
    }

    /**
     * @notice Buy / Fund Escrow: Buyer deposits required funds into the contract vault.
     * Prerequisite State: CREATED
     * Allowed Actor: Buyer ONLY
     */
    function buy() external payable onlyBuyer inState(EscrowStatus.Created) nonReentrant {
        require(msg.value == amount, "Escrow: Deposit must equal exact escrow amount");

        status = EscrowStatus.Funded;
        updatedAt = block.timestamp;

        emit BuyFunded(msg.sender, msg.value, block.timestamp);
    }

    /**
     * @notice Mark Product as Delivered & Start 5-Day Return Window Countdown.
     * Prerequisite State: FUNDED
     * Allowed Actor(s): Seller, Buyer, or Arbiter
     * @param trackingInfo Courier tracking or delivery reference.
     */
    function markDelivered(string calldata trackingInfo) external onlyAuthorizedActor inState(EscrowStatus.Funded) {
        status = EscrowStatus.Delivered;
        deliveredAt = block.timestamp;
        deliveryTrackingInfo = trackingInfo;
        updatedAt = block.timestamp;

        emit ProductDelivered(msg.sender, trackingInfo, deliveredAt, deliveredAt + returnPeriodDuration);
    }

    /**
     * @notice Buyer Return Request during 5-day return window.
     * Prerequisite State: DELIVERED
     * Allowed Actor: Buyer ONLY
     * Time Constraint: Within 5 days of delivery timestamp.
     * @param reason Reason for returning item.
     */
    function requestReturn(string calldata reason) external onlyBuyer inState(EscrowStatus.Delivered) {
        require(
            block.timestamp <= deliveredAt + returnPeriodDuration,
            "Escrow: 5-day return window has expired"
        );
        require(bytes(reason).length > 0, "Escrow: Return reason cannot be empty");

        status = EscrowStatus.Held;
        holdReason = reason;
        updatedAt = block.timestamp;

        emit ReturnRequested(msg.sender, reason, block.timestamp);
    }

    /**
     * @notice Hold Escrow: Freezes/locks escrow state during inspection or dispute.
     * Prerequisite State: CREATED, FUNDED, or DELIVERED
     * Allowed Actor(s): Buyer, Seller, or Arbiter
     * @param reason Mandatory reason for putting the escrow on hold.
     */
    function hold(string calldata reason) external onlyAuthorizedActor {
        require(
            status == EscrowStatus.Created || status == EscrowStatus.Funded || status == EscrowStatus.Delivered,
            "Escrow: Cannot hold from current state"
        );
        require(bytes(reason).length > 0, "Escrow: Hold reason cannot be empty");

        status = EscrowStatus.Held;
        holdReason = reason;
        updatedAt = block.timestamp;

        emit HoldLocked(msg.sender, reason, block.timestamp);
    }

    /**
     * @notice Buyer Early Acceptance: Waives remaining 5-day return period and releases money to Seller.
     * Prerequisite State: DELIVERED
     * Allowed Actor: Buyer ONLY
     */
    function acceptDeliveryEarly(string calldata settlementNotes) external onlyBuyer inState(EscrowStatus.Delivered) nonReentrant {
        _releaseToSeller(msg.sender, settlementNotes);
    }

    /**
     * @notice Sell / Release Funds: Releases vault balance directly to the Seller.
     * Rules:
     * - If DELIVERED: Seller can claim ONLY IF 5 days return period has passed.
     * - Buyer or Arbiter can approve release at any time.
     * Prerequisite State: FUNDED, DELIVERED, or HELD
     * Allowed Actor(s): Buyer, Seller, or Arbiter
     * @param settlementNotes Optional notes for completing settlement.
     */
    function sell(string calldata settlementNotes) external onlyAuthorizedActor nonReentrant {
        if (status == EscrowStatus.Delivered) {
            if (msg.sender == seller) {
                require(
                    block.timestamp >= deliveredAt + returnPeriodDuration,
                    "Escrow: Money is held during 5-day return window. Merchant must wait for return period to expire or get buyer early approval."
                );
            }
        } else if (status == EscrowStatus.Funded) {
            require(
                msg.sender == buyer || msg.sender == arbiter,
                "Escrow: Buyer or Arbiter must approve release or product must be marked delivered first"
            );
        } else if (status == EscrowStatus.Held) {
            require(
                msg.sender == buyer || msg.sender == arbiter,
                "Escrow: Cannot release held funds without buyer or arbiter approval"
            );
        } else {
            revert("Escrow: Invalid state for funds release");
        }

        _releaseToSeller(msg.sender, settlementNotes);
    }

    /**
     * @notice Auto-Release after 5-day return period expires.
     */
    function claimMerchantRelease() external nonReentrant {
        require(status == EscrowStatus.Delivered, "Escrow: Must be in Delivered state");
        require(
            block.timestamp >= deliveredAt + returnPeriodDuration,
            "Escrow: 5-day return window is active. Funds are held."
        );

        _releaseToSeller(seller, "Auto-released to merchant after 5-day return window elapsed");
    }

    /**
     * @notice Refund Buyer: Returns vault balance back to the Buyer.
     * Prerequisite State: FUNDED, DELIVERED, HELD, or DISPUTED
     * Allowed Actor(s): Seller or Arbiter ONLY (Buyer cannot self-refund)
     * @param reason Reason for executing refund.
     */
    function refund(string calldata reason) external onlySellerOrArbiter nonReentrant {
        require(
            status == EscrowStatus.Funded || status == EscrowStatus.Delivered || status == EscrowStatus.Held || status == EscrowStatus.Disputed,
            "Escrow: Cannot refund from current state"
        );
        uint256 vaultBalance = address(this).balance;
        require(vaultBalance >= amount, "Escrow: Insufficient vault balance");

        status = EscrowStatus.Refunded;
        holdReason = "";
        updatedAt = block.timestamp;

        (bool success, ) = buyer.call{value: vaultBalance}("");
        require(success, "Escrow: Failed to refund buyer");

        emit RefundedToBuyer(msg.sender, buyer, vaultBalance, reason);
    }

    /**
     * @dev Internal payout helper.
     */
    function _releaseToSeller(address requestedBy, string memory notes) internal {
        uint256 vaultBalance = address(this).balance;
        require(vaultBalance >= amount, "Escrow: Insufficient vault balance");

        status = EscrowStatus.Released;
        holdReason = "";
        updatedAt = block.timestamp;

        (bool success, ) = seller.call{value: vaultBalance}("");
        require(success, "Escrow: Failed to transfer funds to seller");

        emit SellReleased(requestedBy, seller, vaultBalance, notes);
    }

    /**
     * @notice Get Return Window Details and remaining time.
     */
    function getReturnWindowStatus()
        external
        view
        returns (
            bool isDelivered,
            uint256 deliveredAtTimestamp,
            uint256 returnPeriodSec,
            uint256 expiresAt,
            uint256 secondsRemaining,
            bool merchantCanClaim,
            bool buyerCanReturn
        )
    {
        isDelivered = (status == EscrowStatus.Delivered);
        deliveredAtTimestamp = deliveredAt;
        returnPeriodSec = returnPeriodDuration;

        if (isDelivered) {
            expiresAt = deliveredAt + returnPeriodDuration;
            if (block.timestamp < expiresAt) {
                secondsRemaining = expiresAt - block.timestamp;
                merchantCanClaim = false;
                buyerCanReturn = true;
            } else {
                secondsRemaining = 0;
                merchantCanClaim = true;
                buyerCanReturn = false;
            }
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
            createdAt,
            updatedAt
        );
    }
}
