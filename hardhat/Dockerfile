FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY contracts ./contracts
COPY scripts ./scripts
COPY test ./test
COPY hardhat.config.cjs ./

ARG SKIP_HARDHAT_TESTS=0
RUN npm run compile \
    && if [ "$SKIP_HARDHAT_TESTS" != "1" ]; then npm run test:solidity; fi

EXPOSE 8545

CMD ["npm", "run", "node"]
