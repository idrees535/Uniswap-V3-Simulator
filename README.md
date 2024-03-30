## Introduction
The Uniswap V3 Simulator is a comprehensive tool designed to simulate the functionality of Uniswap V3 pools locally. By deploying Uniswap V3 core contracts and token contracts on Ganache using Ether Brownie, users can interact with these contracts via web3.py and Brownie. The simulator is equipped to perform a variety of actions including creating pools, initializing pools, adding and removing liquidity, collecting fees, performing swaps, and retrieving the global, tick, and positions state of the pool.

In this medium article different components of analysis are discussed: https://medium.com/@idrees535/uniswap-v3-simulator-streamline-your-tokens-pool-launch-with-liquidity-analysis-fa4346d11248

It features several helper functions, such as util, constants, and tx_dict, among others. The core components of this simulator are `UniV3Simulator.py` and `analysis.py`:

- `UniV3Simulator.py`: Manages the deployment of V3 core and token contracts, and contains functions for interacting with Uniswap V3 pools and tokens as well as retrieving pool state information.
- `analysis.ipynb`: Utilized for conducting various analyses, leveraging the functions defined in `UniV3Simulator.py`.

## Setup Instructions

### Prerequisites
- Python 3.10
- Node.js and npm

### Clone the Repository
```bash
git clone https://github.com/idrees535/Uniswap-V3-Simulator.git
```

### Create a Virtual Environment
Navigate to the cloned repository's directory and create a virtual environment:
```bash
python -m venv venv
```
Activate the virtual environment:
- On macOS/Linux: `source venv/bin/activate`

### Install Python Requirements
Install the required Python packages using pip:
```bash
pip install -r requirements_td.txt
or
pip install -r requirements.txt 
```

### Install and Run Ganache CLI
Install Ganache CLI globally using npm:
```bash
npm install -g ganache-cli
```
Then, start Ganache CLI in a separate terminal:
```bash
ganache-cli
```

### Compile Contracts with Brownie
Navigate to the `v3-core` directory and compile the smart contracts using Brownie:
```bash
cd v3-core
brownie compile
```

## Getting Started with Analysis
Once the setup is complete, navigate to the analysis notebook and import `UniV3Simulator`. You are now ready to start working with your analysis.

## Architecture Overview
The simulator's architecture is designed to facilitate local simulation of Uniswap V3 pools by interacting with deployed contracts through web3.py and Brownie. The interactions encompass a wide range of functionalities essential for liquidity pool management and analysis:

### State Functions
- Retrieve global state of the pool, wallet, and contract balances.
- Example usage:
  ```python
  print(ali_usdc_pool1.get_global_state())
  print(ali_usdc_pool1.get_wallet_balances(GOD_ACCOUNT))
  ```

### Action Functions
- Perform actions such as adding single-sided liquidity, adding liquidity with a USD budget, and performing token swaps.
- Example usage:
  ```python
  mint_tx_receipt = ali_usdc_pool1.add_single_sided_liquidity(GOD_ACCOUNT, price_to_valid_tick(price_lower), price_to_valid_tick(price_upper), liquidity_amount, b'')
  tx_dict = ali_usdc_pool1.swap_token0_for_token1(GOD_ACCOUNT, swap_amount, data=b'')
  ```

