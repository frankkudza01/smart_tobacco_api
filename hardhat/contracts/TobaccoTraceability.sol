// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TobaccoTraceability
 * @notice On-chain anchoring for Zimbabwe tobacco supply chain.
 *         Stores hashes for digital twin registration, event anchoring,
 *         document anchoring, and ownership transfer references.
 */
contract TobaccoTraceability {
    address public owner;

    struct Anchor {
        bytes32 dataHash;
        string referenceType;
        string referenceId;
        uint256 timestamp;
        address submitter;
    }

    mapping(bytes32 => Anchor) public anchors;
    mapping(string => bytes32[]) public referenceAnchors;

    /**
     * Merkle-batch anchoring: commit a single root that proves inclusion of
     * many off-chain hashes. ~100x cheaper than per-event anchoring at scale.
     */
    struct BatchAnchor {
        bytes32 merkleRoot;
        uint256 leafCount;
        string batchType;   // e.g. "trace_events", "documents"
        string batchLabel;  // e.g. "events-2026-05-02" — uniqueness key off-chain
        uint256 timestamp;
        address submitter;
    }

    mapping(bytes32 => BatchAnchor) public batchAnchors;

    /**
     * Inspection attestation: TIMB / regulator records that an inspection
     * occurred at a given block height with an opaque off-chain notes URI.
     */
    struct Inspection {
        string lotId;
        bytes32 dataHash;
        uint256 score;          // 0-100
        string notesUri;        // optional pointer to redacted notes (e.g. ipfs://, https://)
        address inspector;
        uint256 timestamp;
    }
    mapping(bytes32 => Inspection) public inspections;

    /**
     * Custody transfer: emit a non-repudiable record that lot ownership moved
     * from `from` to `to`. The off-chain `payloadHash` covers a canonical
     * payload that BOTH parties co-signed (ECDSA, EIP-191) before submission.
     */
    /**
     * Anchor revocation: a regulator/auditor can attach a structured revocation
     * to an existing anchor (does NOT delete the original — both remain auditable).
     */
    struct Revocation {
        bytes32 originalAnchorId;
        bytes32 reasonHash;
        address revoker;
        uint256 timestamp;
    }
    mapping(bytes32 => Revocation) public revocations;
    mapping(bytes32 => bytes32[]) public anchorRevocations;  // originalAnchorId => revocation ids

    event AnchorCreated(
        bytes32 indexed anchorId,
        bytes32 dataHash,
        string referenceType,
        string referenceId,
        address indexed submitter,
        uint256 timestamp
    );

    event BatchRootAnchored(
        bytes32 indexed batchId,
        bytes32 indexed merkleRoot,
        uint256 leafCount,
        string batchType,
        string batchLabel,
        address indexed submitter,
        uint256 timestamp
    );

    event OwnershipTransferred(
        string referenceId,
        address indexed from,
        address indexed to,
        uint256 timestamp
    );

    event InspectionAttested(
        bytes32 indexed inspectionId,
        string lotId,
        address indexed inspector,
        uint256 score,
        bytes32 dataHash,
        string notesUri,
        uint256 timestamp
    );

    event CustodyTransferred(
        string lotId,
        address indexed fromParty,
        address indexed toParty,
        bytes32 payloadHash,
        uint256 weightGrams,
        uint256 timestamp,
        address indexed submitter
    );

    event AnchorRevoked(
        bytes32 indexed originalAnchorId,
        bytes32 indexed revocationId,
        address indexed revoker,
        bytes32 reasonHash,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Not authorized");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function anchorEventHash(
        bytes32 _dataHash,
        string calldata _referenceType,
        string calldata _referenceId
    ) external returns (bytes32) {
        bytes32 anchorId = keccak256(
            abi.encodePacked(_dataHash, _referenceType, _referenceId, block.timestamp, msg.sender)
        );
        require(anchors[anchorId].timestamp == 0, "Anchor already exists");

        anchors[anchorId] = Anchor({
            dataHash: _dataHash,
            referenceType: _referenceType,
            referenceId: _referenceId,
            timestamp: block.timestamp,
            submitter: msg.sender
        });

        referenceAnchors[_referenceId].push(anchorId);

        emit AnchorCreated(anchorId, _dataHash, _referenceType, _referenceId, msg.sender, block.timestamp);
        return anchorId;
    }

    function anchorDocumentHash(
        bytes32 _dataHash,
        string calldata _referenceId
    ) external returns (bytes32) {
        return this.anchorEventHash(_dataHash, "document", _referenceId);
    }

    function registerDigitalTwin(
        bytes32 _dataHash,
        string calldata _lotId
    ) external returns (bytes32) {
        return this.anchorEventHash(_dataHash, "digital_twin", _lotId);
    }

    function verifyAnchor(bytes32 _anchorId) external view returns (
        bytes32 dataHash,
        string memory referenceType,
        string memory referenceId,
        uint256 timestamp,
        address submitter
    ) {
        Anchor storage a = anchors[_anchorId];
        require(a.timestamp != 0, "Anchor not found");
        return (a.dataHash, a.referenceType, a.referenceId, a.timestamp, a.submitter);
    }

    function getAnchorsByReference(string calldata _referenceId)
        external view returns (bytes32[] memory)
    {
        return referenceAnchors[_referenceId];
    }

    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Invalid address");
        owner = _newOwner;
    }

    /**
     * Anchor a Merkle root (e.g. of one day's TraceEvent hashes).
     * The off-chain proof bundle gives consumers an O(log n) inclusion proof
     * for any single leaf without requiring trust in the off-chain database.
     */
    function anchorBatchRoot(
        bytes32 _merkleRoot,
        string calldata _batchType,
        string calldata _batchLabel,
        uint256 _leafCount
    ) external returns (bytes32) {
        bytes32 batchId = keccak256(
            abi.encodePacked(_merkleRoot, _batchType, _batchLabel, block.timestamp, msg.sender)
        );
        require(batchAnchors[batchId].timestamp == 0, "Batch already anchored");

        batchAnchors[batchId] = BatchAnchor({
            merkleRoot: _merkleRoot,
            leafCount: _leafCount,
            batchType: _batchType,
            batchLabel: _batchLabel,
            timestamp: block.timestamp,
            submitter: msg.sender
        });

        emit BatchRootAnchored(
            batchId,
            _merkleRoot,
            _leafCount,
            _batchType,
            _batchLabel,
            msg.sender,
            block.timestamp
        );
        return batchId;
    }

    function verifyBatchRoot(bytes32 _batchId) external view returns (
        bytes32 merkleRoot,
        uint256 leafCount,
        string memory batchType,
        string memory batchLabel,
        uint256 timestamp,
        address submitter
    ) {
        BatchAnchor storage b = batchAnchors[_batchId];
        require(b.timestamp != 0, "Batch not found");
        return (b.merkleRoot, b.leafCount, b.batchType, b.batchLabel, b.timestamp, b.submitter);
    }

    /**
     * Record an inspection attestation. Score is 0..100. The notesUri lets a
     * regulator publish optional redacted detail (off-chain) without leaking PII.
     */
    function attestInspection(
        string calldata _lotId,
        bytes32 _dataHash,
        uint256 _score,
        string calldata _notesUri
    ) external returns (bytes32) {
        require(_score <= 100, "score must be 0-100");
        bytes32 inspectionId = keccak256(
            abi.encodePacked(_lotId, _dataHash, msg.sender, block.timestamp)
        );
        require(inspections[inspectionId].timestamp == 0, "Inspection already attested");

        inspections[inspectionId] = Inspection({
            lotId: _lotId,
            dataHash: _dataHash,
            score: _score,
            notesUri: _notesUri,
            inspector: msg.sender,
            timestamp: block.timestamp
        });

        emit InspectionAttested(
            inspectionId, _lotId, msg.sender, _score, _dataHash, _notesUri, block.timestamp
        );
        return inspectionId;
    }

    function verifyInspection(bytes32 _inspectionId) external view returns (
        string memory lotId,
        bytes32 dataHash,
        uint256 score,
        string memory notesUri,
        address inspector,
        uint256 timestamp
    ) {
        Inspection storage i = inspections[_inspectionId];
        require(i.timestamp != 0, "Inspection not found");
        return (i.lotId, i.dataHash, i.score, i.notesUri, i.inspector, i.timestamp);
    }

    /**
     * Record a custody transfer. The off-chain `_payloadHash` covers a canonical
     * payload that BOTH `_from` and `_to` ECDSA-signed before submission.
     * The contract does not validate the signatures (that happens off-chain) —
     * it only records the non-repudiable on-chain proof that this transfer
     * was made at this block, with this payload hash, by this submitter.
     */
    function recordCustodyTransfer(
        string calldata _lotId,
        address _from,
        address _to,
        bytes32 _payloadHash,
        uint256 _weightGrams,
        uint256 _timestamp
    ) external returns (bytes32) {
        require(_from != address(0) && _to != address(0), "from/to required");
        require(_from != _to, "from == to");
        bytes32 anchorId = this.anchorEventHash(_payloadHash, "custody_transfer", _lotId);
        emit CustodyTransferred(
            _lotId, _from, _to, _payloadHash, _weightGrams, _timestamp, msg.sender
        );
        return anchorId;
    }

    /**
     * Attach a structured revocation to an existing anchor without deleting it.
     * Both records remain on-chain so the audit trail is complete.
     */
    function revokeAnchor(
        bytes32 _originalAnchorId,
        bytes32 _reasonHash
    ) external returns (bytes32) {
        require(anchors[_originalAnchorId].timestamp != 0, "Original anchor not found");
        bytes32 revocationId = keccak256(
            abi.encodePacked(_originalAnchorId, _reasonHash, msg.sender, block.timestamp)
        );
        require(revocations[revocationId].timestamp == 0, "Revocation already exists");

        revocations[revocationId] = Revocation({
            originalAnchorId: _originalAnchorId,
            reasonHash: _reasonHash,
            revoker: msg.sender,
            timestamp: block.timestamp
        });
        anchorRevocations[_originalAnchorId].push(revocationId);

        emit AnchorRevoked(_originalAnchorId, revocationId, msg.sender, _reasonHash, block.timestamp);
        return revocationId;
    }

    function getRevocationsForAnchor(bytes32 _originalAnchorId)
        external view returns (bytes32[] memory)
    {
        return anchorRevocations[_originalAnchorId];
    }
}
