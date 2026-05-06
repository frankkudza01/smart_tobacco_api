const { expect } = require("chai");
const hre = require("hardhat");

describe("TobaccoTraceability", function () {
  it("anchors event hash and reads back via verifyAnchor", async function () {
    const [acc] = await hre.ethers.getSigners();
    const Factory = await hre.ethers.getContractFactory("TobaccoTraceability");
    const c = await Factory.deploy();
    await c.waitForDeployment();

    const dataHash = hre.ethers.keccak256(hre.ethers.toUtf8Bytes("payload"));
    const tx = await c.anchorEventHash(dataHash, "trace_event", "ref-uuid-1");
    const receipt = await tx.wait();
    expect(receipt.status).to.equal(1);

    const anchorId = await c.getAnchorsByReference("ref-uuid-1");
    expect(anchorId.length).to.equal(1);

    const v = await c.verifyAnchor(anchorId[0]);
    expect(v.dataHash).to.equal(dataHash);
    expect(v.referenceType).to.equal("trace_event");
    expect(v.referenceId).to.equal("ref-uuid-1");
    expect(v.submitter).to.equal(acc.address);
  });

  it("anchorDocumentHash stores document reference", async function () {
    const Factory = await hre.ethers.getContractFactory("TobaccoTraceability");
    const c = await Factory.deploy();
    await c.waitForDeployment();

    const dataHash = hre.ethers.keccak256(hre.ethers.toUtf8Bytes("doc-bytes"));
    const tx = await c.anchorDocumentHash(dataHash, "doc-uuid-2");
    await tx.wait();

    const ids = await c.getAnchorsByReference("doc-uuid-2");
    expect(ids.length).to.equal(1);
    const v = await c.verifyAnchor(ids[0]);
    expect(v.referenceType).to.equal("document");
  });
});
