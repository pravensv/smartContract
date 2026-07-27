// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UniversalEscrow
 * @dev Multi-party Escrow Smart Contract matching the Google Cloud Universal Ledger Escrow API lifecycle.
 * Features Create, Buy (Fund), Hold (Freeze), Sell (Release), and Refund operations with role-based access control.
 */
contract UniversalEscrow {
    
    // --- State Enum ---
    enum EscrowStatus {
        Created,   // 0: Initialized, awaiting funding
        Funded,    // 1: Buyer deposited funds into vault
        Held,      // 2: Locked during inspection or dispute
        Released,  // 3: Funds settled and sent to Seller
        Refunded,  // 4: Funds returned to Buyer
        Disputed   // 5: Dispute flagged by parties
    }

    // --- State Variables ---
    address payable public immutable buyer;
    address payable public immutable seller;
    address public immutable arbiter;
    uint256 public immutable amount;
    string public title;

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
        string title
    );
    event BuyFunded(address indexed buyer, uint256 amount, uint256 timestamp);
    event HoldLocked(address indexed requestedBy, string reason, uint256 timestamp);
    event SellReleased(address indexed requestedBy, address indexed seller, uint256 amount, string notes);
    event RefundedToBuyer(address indexed requestedBy, address indexed buyer, uint256 amount, string reason);

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
        require(_amount > 0, "Escrow: Amount must be greater than zero");

        buyer = payable(msg.sender);
        seller = _seller;
        arbiter = _arbiter;
        amount = _amount;
        title = _title;

        status = EscrowStatus.Created;
        createdAt = block.timestamp;
        updatedAt = block.timestamp;

        emit EscrowCreated(msg.sender, _seller, _arbiter, _amount, _title);
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
     * @notice Hold Escrow: Freezes/locks escrow state during inspection or dispute.
     * Prerequisite State: CREATED or FUNDED
     * Allowed Actor(s): Buyer, Seller, or Arbiter
     * @param reason Mandatory reason for putting the escrow on hold.
     */
    function hold(string calldata reason) external onlyAuthorizedActor {
        require(
            status == EscrowStatus.Created || status == EscrowStatus.Funded,
            "Escrow: Cannot hold from current state"
        );
        require(bytes(reason).length > 0, "Escrow: Hold reason cannot be empty");

        status = EscrowStatus.Held;
        holdReason = reason;
        updatedAt = block.timestamp;

        emit HoldLocked(msg.sender, reason, block.timestamp);
    }

    /**
     * @notice Sell / Release Funds: Releases vault balance directly to the Seller.
     * Prerequisite State: FUNDED or HELD
     * Allowed Actor(s): Buyer, Seller, or Arbiter
     * @param settlementNotes Optional notes for completing settlement.
     */
    function sell(string calldata settlementNotes) external onlyAuthorizedActor nonReentrant {
        require(
            status == EscrowStatus.Funded || status == EscrowStatus.Held,
            "Escrow: Cannot release funds from current state"
        );
        uint256 vaultBalance = address(this).balance;
        require(vaultBalance >= amount, "Escrow: Insufficient vault balance");

        status = EscrowStatus.Released;
        holdReason = "";
        updatedAt = block.timestamp;

        (bool success, ) = seller.call{value: vaultBalance}("");
        require(success, "Escrow: Failed to transfer funds to seller");

        emit SellReleased(msg.sender, seller, vaultBalance, settlementNotes);
    }

    /**
     * @notice Refund Buyer: Returns vault balance back to the Buyer.
     * Prerequisite State: FUNDED, HELD, or DISPUTED
     * Allowed Actor(s): Seller or Arbiter ONLY (Buyer cannot self-refund)
     * @param reason Reason for executing refund.
     */
    function refund(string calldata reason) external onlySellerOrArbiter nonReentrant {
        require(
            status == EscrowStatus.Funded || status == EscrowStatus.Held || status == EscrowStatus.Disputed,
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
