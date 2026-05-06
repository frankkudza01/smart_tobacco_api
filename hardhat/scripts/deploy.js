/**
 * Deploy TobaccoTraceability to localhost (or any network in hardhat.config).
 *
 * Localhost (after `npx hardhat node`):
 *   npx hardhat run scripts/deploy.js --network localhost
 *
 * Docker Compose (RPC hostname `hardhat`):
 *   npx hardhat run scripts/deploy.js --network docker
 *   Use HARDHAT_RPC_URL if the JSON-RPC URL differs from http://hardhat:8545.
 *
 * Copy the printed env snippet into backend/.env when using BLOCKCHAIN_ENABLED=True.
 */const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  const bal = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance:", hre.ethers.formatEther(bal), "ETH");

  const Factory = await hre.ethers.getContractFactory("TobaccoTraceability");
  const contract = await Factory.deploy();
  await contract.waitForDeployment();
  const address = await contract.getAddress();

  console.log("\nTobaccoTraceability deployed to:", address);

  const net = await hre.ethers.provider.getNetwork();
  const pk = process.env.HARDHAT_DEPLOYER_PK;
  const deployerPkLine = pk
    ? `BLOCKCHAIN_PRIVATE_KEY=${pk}`
    : `# First Hardhat account (default) — export from hardhat node startup logs:\nBLOCKCHAIN_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80`;

  const isDockerNet = hre.network.name === "docker";
  const djangoRpcDocker = "http://hardhat:8545";
  const djangoRpcHost = "http://127.0.0.1:8545";
  const djangoRpcPrimary = isDockerNet ? djangoRpcDocker : djangoRpcHost;

  const snippet = `
# --- Add to backend/.env (or .env.production) when BLOCKCHAIN_ENABLED=True ---
BLOCKCHAIN_ENABLED=True
BLOCKCHAIN_PROVIDER_URL=${djangoRpcPrimary}
BLOCKCHAIN_CHAIN_ID=${net.chainId}
BLOCKCHAIN_CONTRACT_ADDRESS=${address}
${deployerPkLine}
${isDockerNet ? `# From your PC (host) against bound port 8545, use instead:\n# BLOCKCHAIN_PROVIDER_URL=${djangoRpcHost}\n` : ""}`;

  console.log(snippet);

  const outDir = path.join(__dirname, "..");
  const defaultName = isDockerNet ? "deployment-docker.json" : "deployment-localhost.json";
  const outFile =
    process.env.HARDHAT_DEPLOYMENT_JSON_OUT || path.join(outDir, defaultName);
  fs.writeFileSync(
    outFile,
    JSON.stringify(
      {
        contractAddress: address,
        chainId: Number(net.chainId),
        deployer: deployer.address,
        network: hre.network.name,
      },
      null,
      2
    )
  );
  console.log("Wrote", outFile);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
