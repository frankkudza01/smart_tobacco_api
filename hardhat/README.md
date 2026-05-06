# Hardhat — local blockchain for Django anchoring tests

This folder compiles and deploys `TobaccoTraceability.sol` so the Django app can run **`BLOCKCHAIN_ENABLED=True`** against a real JSON-RPC node.

## Prerequisites

- Node.js 18+ and npm

## Install

```bash
cd hardhat
npm install
```

## Compile & Solidity tests

```bash
npm run compile
npm run test:solidity
```

## Run a local chain + deploy (typical workflow)

**Terminal 1 — keep running:**

```bash
npm run node
```

This starts Hardhat Network at `http://127.0.0.1:8545` with **chain ID `31337`**.

**Terminal 2 — deploy contract:**

```bash
npm run deploy:local
```

Copy the printed `BLOCKCHAIN_*` lines into `backend/.env`. Use the **first test account private key** shown when `hardhat node` starts (or set `HARDHAT_DEPLOYER_PK` when running deploy if you use a custom signer).

The script also writes `deployment-localhost.json` with the contract address.

## Django alignment

| Variable | Hardhat local value |
|----------|---------------------|
| `BLOCKCHAIN_ENABLED` | `True` |
| `BLOCKCHAIN_PROVIDER_URL` | `http://127.0.0.1:8545` |
| `BLOCKCHAIN_CHAIN_ID` | `31337` |
| `BLOCKCHAIN_CONTRACT_ADDRESS` | from deploy output |
| `BLOCKCHAIN_PRIVATE_KEY` | first account PK from `hardhat node` logs |

Restart Django and **Celery worker** after changing `.env`. Anchoring tasks call the contract via ABI-encoded transactions.

## Default Hardhat account #0 (development only)

```
0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

Never use this on any public network.
