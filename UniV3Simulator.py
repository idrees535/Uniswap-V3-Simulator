import sys
from constants import BROWNIE_PROJECTUniV3, GOD_ACCOUNT
from base18 import toBase18, fromBase18,fromBase128,price_to_valid_tick,price_to_raw_tick,price_to_sqrtp,sqrtp_to_price,tick_to_sqrtp,liquidity0,liquidity1,eth,tick_to_price
import brownie
from web3 import Web3
import json
import math
import random
import pandas as pd
from brownie.exceptions import VirtualMachineError
from tx import txdict
from enforce_typing import enforce_types
import numpy as np
import math


class UniV3Simulator():
    def __init__(self, token0='token0', token1='token1', token0_decimals=18, token1_decimals=18, supply_token0=1e18, supply_token1=1e18, fee_tier=3000, initial_pool_price=1,deployer=GOD_ACCOUNT,sync_pool_with_liq=False, initial_liquidity_amount=0):
        self.deployer = deployer
        self.token0_name = token0
        self.token1_name = token1
        self.token0_symbol = token0
        self.token1_symbol = token1
        self.token0_decimals = token0_decimals
        self.token1_decimals = token1_decimals
        self.supply_token0 = supply_token0
        self.supply_token1 = supply_token1
        self.fee_tier = fee_tier
        self.initial_pool_price = initial_pool_price
        self.sync_pool_with_liq=sync_pool_with_liq
        
        self.initial_liquidity_amount=initial_liquidity_amount
        self.pool_id = f"{token0}_{token1}_{fee_tier}"

        w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
        self.base_fee = w3.eth.get_block('latest')['baseFeePerGas']
        
        self.ensure_valid_json_file("model_storage/token_pool_addresses.json")
        self.ensure_valid_json_file("model_storage/liq_positions.json")
        
        self.deploy_load_tokens()
        self.deploy_load_pool()


    def ensure_valid_json_file(self, filepath, default_content="{}"):
        """
        Ensure the file contains valid JSON.
        If the file doesn't exist or contains invalid JSON, 
        initialize it with default_content.
        """
        try:
            with open(filepath, "r") as f:
                content = f.read().strip()  # Read and remove any leading/trailing whitespace
                if not content:  # Check if file is empty
                    raise ValueError("File is empty")
                json.loads(content)  # Try to parse the JSON
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            with open(filepath, "w") as f:  # Create or overwrite the file
                f.write(default_content)

    
    def load_addresses(self):
        try:
            with open("model_storage/token_pool_addresses.json", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_addresses(self, addresses):
        with open("model_storage/token_pool_addresses.json", "w") as f:
            json.dump(addresses, f)

    def deploy_load_tokens(self):
        SimpleToken = BROWNIE_PROJECTUniV3.Simpletoken
        addresses = self.load_addresses()
        pool_addresses = addresses.get(self.pool_id, {})

        # This function deploys a token and saves its address in the JSON file
        def deploy_and_save_token(name, symbol, decimals, supply, key):
            token = SimpleToken.deploy(name, symbol, decimals, toBase18(supply),  {'from': self.deployer, 'gas_price': self.base_fee + 1})
            print(f"New {symbol} token deployed at {token.address}")
            pool_addresses[key] = token.address
            addresses[self.pool_id] = pool_addresses
            self.save_addresses(addresses)
            return token

        # Load or deploy token1
        if "token1_address" in pool_addresses:
            self.token1 = SimpleToken.at(pool_addresses["token1_address"])
        else:
            self.token1 = deploy_and_save_token(self.token1_name, self.token1_symbol, self.token1_decimals, self.supply_token1, "token1_address")

        # Load or deploy token0
        if "token0_address" in pool_addresses:
            self.token0 = SimpleToken.at(pool_addresses["token0_address"])
        else:
            self.token0 = deploy_and_save_token(self.token0_name, self.token0_symbol, self.token0_decimals, self.supply_token0, "token0_address")
            # Ensure token0 address is less than token1 address
            while int(self.token0.address, 16) >= int(self.token1.address, 16):
                self.token0 = deploy_and_save_token(self.token0_name, self.token0_symbol, self.token0_decimals, self.supply_token0, "token0_address")


    def deploy_load_pool(self):
        UniswapV3Factory = BROWNIE_PROJECTUniV3.UniswapV3Factory
        UniswapV3Pool = BROWNIE_PROJECTUniV3.UniswapV3Pool
        addresses = self.load_addresses()
        pool_addresses = addresses.get(self.pool_id, {})

        if "pool_address" in pool_addresses:
            self.pool = UniswapV3Pool.at(pool_addresses["pool_address"])
            print(f"Existing pool:{self.pool_id} having pool address: {self.pool} loaded")
        else:
            self.factory = UniswapV3Factory.deploy( {'from': self.deployer, 'gas_price': self.base_fee + 1})
            pool_creation_txn = self.factory.createPool(self.token0.address, self.token1.address, self.fee_tier,  {'from': self.deployer, 'gas_price': self.base_fee + 1})
            self.pool_address = pool_creation_txn.events['PoolCreated']['pool']
            print(pool_creation_txn.events)
            self.pool = UniswapV3Pool.at(self.pool_address)

            sqrtPriceX96 = price_to_sqrtp(self.initial_pool_price)
            tx_receipt=self.pool.initialize(sqrtPriceX96,  {'from': self.deployer, 'gas_price': self.base_fee + 100000})
            print(tx_receipt.events)

            pool_addresses["pool_address"] = self.pool_address
            addresses[self.pool_id] = pool_addresses
            self.save_addresses(addresses)
            
            #self.sync_pool_state()


    def ensure_token_order(self):
        # Check if token0's address is greater than token1's address
        if int(self.token0.address, 16) > int(self.token1.address, 16):
            SimpleToken = BROWNIE_PROJECTUniV3.Simpletoken

            # Continue deploying token0 until its address is less than token1's address
            while True:
                new_token0 = SimpleToken.deploy(self.token0_name, self.token0_symbol, self.token0_decimals, self.supply_token0, {'from': self.deployer, 'gas_price': self.base_fee + 1})
                if int(new_token0.address, 16) < int(self.token1.address, 16):
                    break

            # Update the model's token0 reference to point to the new token0 contract
            self.token0 = new_token0
            print(f"New {self.token0_symbol} token deployed at {self.token0.address} to ensure desired token order in the pool")

    def sync_pool_state(self):
        # Can add any other logic to sync pool with real pool
        if self.sync_pool_with_liq:
            num_positions = 20
            price_increment = 0.05  # 5% price increment

            # Loop through positions
            for position in range(1, num_positions + 1):
                # Calculate price range
                price_lower = self.initial_pool_price - (price_increment * position * self.initial_pool_price)
                price_upper = self.initial_pool_price + (price_increment * position * self.initial_pool_price)

                if price_lower<=0:
                    price_lower=random.uniform(0.1,1.0)
                if price_upper<=0:
                    price_upper=random.uniform(0.1,1.0)

                liquidity_amount = self.initial_liquidity_amount * random.uniform(0.5,1.5)

                # Convert prices to ticks
                tick_lower = price_to_valid_tick(price_lower)
                tick_upper = price_to_valid_tick(price_upper)

                # Add liquidity
                self.add_liquidity(self.deployer, tick_lower, tick_upper, liquidity_amount, b'')
                print(f'Position {position}: Added liquidity amount {liquidity_amount} in the price range {price_lower} to {price_upper}')


        else:
            print("No pool sync applied")


    def add_liquidity(self, liquidity_provider, tick_lower, tick_upper, usd_budget, data):
        tx_params = {'from': str(liquidity_provider), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_params1 = {'from': str(GOD_ACCOUNT), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_receipt=None
        try:
            pool_actions = self.pool
            liquidity=self.budget_to_liquidity(tick_lower,tick_upper,usd_budget)
            #print(liquidity)

            tx_receipt = pool_actions.mint(liquidity_provider, tick_lower, tick_upper, liquidity, data, tx_params)

            # Implement callback
            amount0 = tx_receipt.events['Mint']['amount0']
            amount1 = tx_receipt.events['Mint']['amount1']
            #print(tx_receipt.events['Mint']['amount'])
            print(tx_receipt.events)
            if amount0 > 0:
                tx_receipt_token0_transfer = self.token0.transfer(self.pool.address, amount0, tx_params)
            if amount1 > 0:
                tx_receipt_token1_transfer=self.token1.transfer(self.pool.address, amount1, tx_params)
                #print(f'token1 amount:{amount1}transfered to contract:{tx_receipt_token1_transfer}')

        except VirtualMachineError as e:
            print("Failed to add liquidty", e.revert_msg)

        # Store position in json file
        liquidity_provider_str = str(liquidity_provider)
        
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            all_positions = {}
        
        # Initialize if this pool_id is not in the list
        if self.pool_id not in all_positions:
            all_positions[self.pool_id] = {}
        
        # Initialize if this liquidity provider is not in the list
        if liquidity_provider_str not in all_positions[self.pool_id]:
            all_positions[self.pool_id][liquidity_provider_str] = []
        
        existing_position = None
        for position in all_positions[self.pool_id][liquidity_provider_str]:
            if position['tick_lower'] == tick_lower and position['tick_upper'] == tick_upper:
                existing_position = position
                break
    
        if existing_position:
            existing_position['liquidity'] += liquidity 
            existing_position['amount_usd'] += usd_budget # Add new liquidity to existing position
        else:
        # Add new position to list
            all_positions[self.pool_id][liquidity_provider_str].append({
                'tick_lower': tick_lower,
                'tick_upper': tick_upper,
                'liquidity': liquidity,
                'amount_usd':usd_budget
            })
        
        # Store updated positions
        with open("model_storage/liq_positions.json", "w") as f:
            json.dump(all_positions, f)
        
        return tx_receipt
    
    # Instead of budget unlike in above function it takes the exact amount of token0 an token1 for single sided liquidty positions (Only applicabe for single sided positions)
    def add_single_sided_liquidity(self, liquidity_provider, tick_lower, tick_upper, usd_budget, data):
        tx_params = {'from': str(liquidity_provider), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_params1 = {'from': str(GOD_ACCOUNT), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_receipt=None
        try:
            pool_actions = self.pool
            liquidity=self.budget_to_liquidity_single_sided(tick_lower,tick_upper,usd_budget)
            #print(liquidity)

            tx_receipt = pool_actions.mint(liquidity_provider, tick_lower, tick_upper, liquidity, data, tx_params)

            # Implement callback
            amount0 = tx_receipt.events['Mint']['amount0']
            amount1 = tx_receipt.events['Mint']['amount1']
            #print(tx_receipt.events['Mint']['amount'])
            print(tx_receipt.events)
            if amount0 > 0:
                tx_receipt_token0_transfer = self.token0.transfer(self.pool.address, amount0, tx_params)
                print(f'token1 amount:{amount0}transfered to contract:{tx_receipt_token0_transfer}')
            if amount1 > 0:
                tx_receipt_token1_transfer=self.token1.transfer(self.pool.address, amount1, tx_params)
                print(f'token1 amount:{amount1}transfered to contract:{tx_receipt_token1_transfer}')

        except VirtualMachineError as e:
            print("Failed to add liquidty", e.revert_msg)

        # Store position in json file
        liquidity_provider_str = str(liquidity_provider)
        
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            all_positions = {}
        
        # Initialize if this pool_id is not in the list
        if self.pool_id not in all_positions:
            all_positions[self.pool_id] = {}
        
        # Initialize if this liquidity provider is not in the list
        if liquidity_provider_str not in all_positions[self.pool_id]:
            all_positions[self.pool_id][liquidity_provider_str] = []
        
        existing_position = None
        for position in all_positions[self.pool_id][liquidity_provider_str]:
            if position['tick_lower'] == tick_lower and position['tick_upper'] == tick_upper:
                existing_position = position
                break
    
        if existing_position:
            existing_position['liquidity'] += liquidity 
            existing_position['amount_usd'] += usd_budget # Add new liquidity to existing position
        else:
        # Add new position to list
            all_positions[self.pool_id][liquidity_provider_str].append({
                'tick_lower': tick_lower,
                'tick_upper': tick_upper,
                'liquidity': liquidity,
                'amount_usd':usd_budget
            })
        
        # Store updated positions
        with open("model_storage/liq_positions.json", "w") as f:
            json.dump(all_positions, f)
        
        return tx_receipt
    
    def add_liquidity_with_liquidity(self, liquidity_provider, tick_lower, tick_upper, liquidity, data):
        tx_params = {'from': str(liquidity_provider), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_params1 = {'from': str(GOD_ACCOUNT), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_receipt=None
        try:
            pool_actions = self.pool
            liquidity=liquidity

            tx_receipt = pool_actions.mint(liquidity_provider, tick_lower, tick_upper, liquidity, data, tx_params)

            # Implement callback
            amount0 = tx_receipt.events['Mint']['amount0']
            amount1 = tx_receipt.events['Mint']['amount1']
            print(tx_receipt.events)
            if amount0 > 0:
                tx_receipt_token0_transfer = self.token0.transfer(self.pool.address, amount0, tx_params)
            if amount1 > 0:
                tx_receipt_token1_transfer=self.token1.transfer(self.pool.address, amount1, tx_params)
                #print(f'token1 amount:{amount1}transfered to contract:{tx_receipt_token1_transfer}')


        except VirtualMachineError as e:
            print("Failed to add liquidty", e.revert_msg)

        # Store position in json file
        liquidity_provider_str = str(liquidity_provider)
       
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            all_positions = {}
        
        # Initialize if this pool_id is not in the list
        if self.pool_id not in all_positions:
            all_positions[self.pool_id] = {}
        
        # Initialize if this liquidity provider is not in the list
        if liquidity_provider_str not in all_positions[self.pool_id]:
            all_positions[self.pool_id][liquidity_provider_str] = []
        
        existing_position = None
        for position in all_positions[self.pool_id][liquidity_provider_str]:
            if position['tick_lower'] == tick_lower and position['tick_upper'] == tick_upper:
                existing_position = position
                break
    
        if existing_position:
            existing_position['liquidity'] += liquidity 
            existing_position['amount_usd'] += liquidity # Add new liquidity to existing position
        else:
        # Add new position to list
            all_positions[self.pool_id][liquidity_provider_str].append({
                'tick_lower': tick_lower,
                'tick_upper': tick_upper,
                'liquidity': liquidity,
                'amount_usd':liquidity
            })
        
        # Store updated positions
        with open("model_storage/liq_positions.json", "w") as f:
            json.dump(all_positions, f)
        
        return tx_receipt
    
    
    def remove_liquidity(self, liquidity_provider, tick_lower, tick_upper, amount_usd):
        liquidity_provider_str = str(liquidity_provider)
        tx_receipt = None
        
        # Convert budget to liquidity amount
        liquidity = self.budget_to_liquidity(tick_lower, tick_upper, amount_usd)

        try:
            tx_params = {'from': str(liquidity_provider), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
            tx_receipt = self.pool.burn(tick_lower, tick_upper, liquidity, tx_params)
            print(tx_receipt.events)
            #if collect_tokens==True:
           #     self.collect_fee(liquidity_provider_str,tick_lower,tick_upper,poke=False)

        except VirtualMachineError as e:
            print("Failed to remove liquidity", e.revert_msg)
            return tx_receipt  # Exit early if smart contract interaction fails

        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            all_positions = {}
            
        if self.pool_id not in all_positions or \
        liquidity_provider_str not in all_positions[self.pool_id]:
            print("Position not found.")
            return tx_receipt  # Exit early if no positions are found

        existing_position = None
        for position in all_positions[self.pool_id][liquidity_provider_str]:
            if position['tick_lower'] == tick_lower and position['tick_upper'] == tick_upper:
                existing_position = position
                break

        if not existing_position:
            print("Position not found.")
            return tx_receipt  # Exit early if the specific position is not found

        if existing_position['liquidity'] > liquidity:
            existing_position['liquidity'] -= liquidity
            existing_position['amount_usd'] -= amount_usd  # Deduct removed liquidity
        else:
            all_positions[self.pool_id][liquidity_provider_str].remove(existing_position)  # Remove position if liquidity becomes zero
        
        # Update the JSON file
        with open("model_storage/liq_positions.json", "w") as f:
            json.dump(all_positions, f)

        return tx_receipt
    
    def remove_liquidity_with_liquidty(self, liquidity_provider, tick_lower, tick_upper, liquidity,collect_tokens=True):
        liquidity_provider_str = str(liquidity_provider)
        tx_receipt = None
        
        # Convert budget to liquidity amount

        try:
            tx_params = {'from': str(liquidity_provider), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
            tx_receipt = self.pool.burn(tick_lower, tick_upper, liquidity, tx_params)
            print(tx_receipt.events)
           #if collect_tokens==True:
           #     self.collect_fee(liquidity_provider_str,tick_lower,tick_upper,poke=False)
        except VirtualMachineError as e:
            print("Failed to remove liquidity", e.revert_msg)
            return tx_receipt  # Exit early if smart contract interaction fails

        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            all_positions = {}
            
        if self.pool_id not in all_positions or \
        liquidity_provider_str not in all_positions[self.pool_id]:
            print("Position not found.")
            return tx_receipt  # Exit early if no positions are found

        existing_position = None
        for position in all_positions[self.pool_id][liquidity_provider_str]:
            if position['tick_lower'] == tick_lower and position['tick_upper'] == tick_upper:
                existing_position = position
                break

        if not existing_position:
            print("Position not found.")
            return tx_receipt  # Exit early if the specific position is not found

        if existing_position['liquidity'] > liquidity:
            existing_position['liquidity'] -= liquidity
            existing_position['amount_usd'] -= liquidity  # Deduct removed liquidity
        else:
            all_positions[self.pool_id][liquidity_provider_str].remove(existing_position)  # Remove position if liquidity becomes zero
        
        # Update the JSON file
        with open("model_storage/liq_positions.json", "w") as f:
            json.dump(all_positions, f)

        return tx_receipt
            

    def swap_token0_for_token1(self, recipient, amount_specified, data):
        tx_params = {'from': str(recipient), 'gas_price': self.base_fee + 1000000, 'gas_limit':  5000000, 'allow_revert': True}
        #tx_params1={'from': str(GOD_ACCOUNT), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        sqrt_price_limit_x96=4295128740+1

        pool_actions = self.pool
        zero_for_one = True
        tx_receipt=None
        
        try:
            tx_receipt= pool_actions.swap(recipient, zero_for_one, amount_specified,sqrt_price_limit_x96, data,tx_params)
            
            print(tx_receipt.events)
            amount0 = tx_receipt.events['Swap']['amount0']

            # Transfer token0 to pool (callback)
            tx_receipt_token0_transfer = self.token0.transfer(self.pool.address, amount0, tx_params)
            
        
        except VirtualMachineError as e:
            print("Swap token 0 to Token 1 Transaction failed:", e.revert_msg)
            slot0_data = self.pool.slot0()
            print(f'contract_token1_balance - approx_token1_amount: {self.token1.balanceOf(self.pool)-amount_specified*sqrtp_to_price(slot0_data[0])}, approx_token1_amount: {amount_specified*sqrtp_to_price(slot0_data[0])}), contract_token1_balance: {self.token1.balanceOf(self.pool)}, amount_swap_token0: {amount_specified}, contract_token0 _balance - amount_swap_token0: {self.token0.balanceOf(self.pool)-amount_specified}')

        return tx_receipt
     
    def swap_token1_for_token0(self, recipient, amount_specified, data):
        tx_params = {'from': str(recipient), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        tx_params1={'from': str(GOD_ACCOUNT), 'gas_price': self.base_fee + 1, 'gas_limit': 5000000, 'allow_revert': True}
        sqrt_price_limit_x96=1461446703485210103287273052203988822378723970342-1

        pool_actions = self.pool   
        zero_for_one = False
        tx_receipt=None 

        try:
            tx_receipt = pool_actions.swap(recipient, zero_for_one, amount_specified, sqrt_price_limit_x96, data,tx_params)
            print(tx_receipt.events)
        
            amount1 = tx_receipt.events['Swap']['amount1']

            # Trasfer token1 to pool (callabck)
            tx_receipt_token1_transfer = self.token1.transfer(self.pool.address, amount1, tx_params)
        except VirtualMachineError as e:
            print("Swap token 1 to Token 0 Transaction failed:", e.revert_msg)
            slot0_data = self.pool.slot0()
            print(f'contract_token0_balance - approx_token0_amount: {self.token0.balanceOf(self.pool)-amount_specified/sqrtp_to_price(slot0_data[0])}, approx_token0_amount: {amount_specified/sqrtp_to_price(slot0_data[0])}, contract_token0_balance: {self.token0.balanceOf(self.pool)}, contract_token1_balance - amount_swap_token1: {self.token1.balanceOf(self.pool)-amount_specified}')
        return tx_receipt

    def collect_fee(self,recipient,tick_lower,tick_upper,poke=False):
        tx_params = {'from': str(recipient), 'gas_price': self.base_fee + 1, 'gas_limit': 500000000, 'allow_revert': True}
        
        # Poke to update variables
        if poke==True:
            try:
                self.pool.burn(tick_lower, tick_upper, 0, tx_params)
            except VirtualMachineError as e:
                print("Poke:", e.revert_msg)
        
        position_key = Web3.solidityKeccak(['address', 'int24', 'int24'], [str(recipient), tick_lower, tick_upper]).hex()

        position_info = self.pool.positions(position_key)
        
        amount0Owed = position_info[3]
        amount1Owed = position_info[4]

        print(f'amount0Owed: {position_info[3]}, ,amount1Owed: {position_info[4]}')

        tx_receipt=None
        fee_collected_usd=0
        try:
            tx_receipt=self.pool.collect(recipient,tick_lower,tick_upper,amount0Owed, amount1Owed,tx_params)
            print(tx_receipt.events)

            amount0Collected=tx_receipt.events['Collect']['amount0']
            amount1Collected=tx_receipt.events['Collect']['amount1']

            slot0_data = self.pool.slot0()
            fee_collected_usd = fromBase18(amount0Collected*sqrtp_to_price(slot0_data[0]) + amount1Collected)
        except VirtualMachineError as e:
            print("Fee collection failed:", e.revert_msg)
            print(f"contract_token0_balance - amount0Owed: {self.token0.balanceOf(self.pool)-amount0Owed} ,contract_token1_balance - amount1Owed: {self.token1.balanceOf(self.pool)-amount1Owed}, position_tick_lower: {tick_lower}, position_tick_upper: {tick_upper}")

        return tx_receipt,fee_collected_usd 
    # Get All positions of all LPs in the pool
    def get_all_liquidity_positions(self):
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            print("No positions found.")
            return {}
        except json.JSONDecodeError:
            print("Error decoding JSON. File might be malformed.")
            return {}

        if self.pool_id in all_positions:
            return all_positions[self.pool_id]
        else:
            print(f"No positions found for pool {self.pool_id}.")
            return {}

    # Get all positions of an LP in the pool
    def get_lp_all_positions(self, liquidity_provider):
        liquidity_provider_str = str(liquidity_provider)
        all_positions = self.get_all_liquidity_positions()

        if not all_positions:
            print("Pool has no LP positions.")
            return None

        if liquidity_provider_str in all_positions:
            return all_positions[liquidity_provider_str]
        else:
            print(f"No positions found for this liquidity provider {liquidity_provider_str} in pool.")
            return None

    def get_position_state(self,tick_lower,tick_upper,agent):
        position_key = Web3.solidityKeccak(['address', 'int24', 'int24'], [str(agent), tick_lower, tick_upper]).hex()
        pool_state = self.pool
        position_info = self.pool.positions(position_key)
        
        return {
        "position_key":f"{str(agent)}_{tick_lower}_{tick_upper}",
        "liquidity_provider": str(agent),
        "tick_lower":tick_lower,
        "tick_upper":tick_upper,
        "_liquidity_raw": position_info[0],
        #"_liquidity_converted": fromBase18(position_info[0]),
        "feeGrowthInside0LastX128": position_info[1],
        #"feeGrowthInside0Last": fromBase128(position_info[1]),
        "feeGrowthInside1LastX128": position_info[2],
        #"feeGrowthInside1Last": fromBase128(position_info[2]),
        "tokensOwed0_raw": position_info[3],
        #"tokensOwed0_converted": fromBase18(position_info[3]),
        "tokensOwed1_raw": position_info[4],
        #"tokensOwed1_converted": fromBase18(position_info[4])
    }


    def get_tick_state(self,tick):
        pool_state = self.pool
        word_position = tick >> 8

        tick_info = pool_state.ticks(tick)
        tick_bitmap = pool_state.tickBitmap(word_position)

        return {
        'tick':tick,
        "liquidityGross_raw": tick_info[0],
        #"liquidityGross_converted": fromBase18(tick_info[0]),
        "liquidityNet_raw": tick_info[1],
        #"liquidityNet_converted": fromBase18(tick_info[1]),
        "feeGrowthOutside0X128": tick_info[2],
        #"feeGrowthOutside0": fromBase128(tick_info[2]),
        "feeGrowthOutside1X128": tick_info[3],
        #"feeGrowthOutside1": fromBase128(tick_info[3]),
        "tickCumulativeOutside": tick_info[4],
        #"secondsPerLiquidityOutsideX128": tick_info[5],
        #"secondsPerLiquidityOutside": fromBase128(tick_info[5]),
        #"secondsOutside": tick_info[6],
        #"initialized": tick_info[7],
        "tickBitmap": tick_bitmap
    }
    
    def get_global_state(self):
        pool_state = self.pool
        slot0_data = pool_state.slot0()
        observation_index = slot0_data[2]

        feeGrowthGlobal0X128 = pool_state.feeGrowthGlobal0X128()
        feeGrowthGlobal1X128 = pool_state.feeGrowthGlobal1X128()
        protocol_fees = pool_state.protocolFees()
        
        liquidity = pool_state.liquidity()

        observation_info = pool_state.observations(observation_index)
        
        return {
        "curr_sqrtPriceX96": slot0_data[0],
        "curr_price": sqrtp_to_price(slot0_data[0]),
        "tick": slot0_data[1],
        #"locking_status": slot0_data[6],
        "feeGrowthGlobal0X128": feeGrowthGlobal0X128,
        #"feeGrowthGlobal0": fromBase128(feeGrowthGlobal0X128),
        "feeGrowthGlobal1X128": feeGrowthGlobal1X128,
        #"feeGrowthGlobal1": fromBase128(feeGrowthGlobal1X128),
        "liquidity_raw": liquidity,
        #"liquidity_converted": fromBase18(liquidity),
        "blockTimestamp": observation_info[0],
        "tickCumulative": observation_info[1],
        "secondsPerLiquidityCumulativeX128": observation_info[2],
        #"secondsPerLiquidityCumulative": fromBase128(observation_info[2]),
        #"initialized": observation_info[3]
    }
           
    def get_pool_state_for_all_ticks(self, lower_price_interested, upper_price_interested):
        tick_states = {} 
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                file_content = f.read().strip()  # Read and remove any leading/trailing whitespace
                if not file_content:  # Check if file is empty
                    print("File is empty. Returning.")
                    return tick_states  # Return empty dict
                all_positions = json.loads(file_content)
        except FileNotFoundError:
            print("No positions found.")
            return tick_states  # Return empty dict
        except json.JSONDecodeError:
            print("Error decoding JSON. File might be malformed.")
            return tick_states  # Return empty dict

        # Convert interested prices to ticks
        lower_tick_interested = price_to_valid_tick(lower_price_interested, tick_spacing=60)
        upper_tick_interested = price_to_valid_tick(upper_price_interested, tick_spacing=60)

        unique_ticks = set()

        # Filter only the positions related to this specific pool.
        if self.pool_id not in all_positions:
            print("No positions for this pool.")
            return tick_states

        for liquidity_provider, positions in all_positions[self.pool_id].items():
            for position in positions:
                tick_lower = position['tick_lower']
                tick_upper = position['tick_upper']

                # Check if the tick_lower or tick_upper falls within the interested range
                if lower_tick_interested <= tick_lower <= upper_tick_interested or \
                lower_tick_interested <= tick_upper <= upper_tick_interested:
                    unique_ticks.add(tick_lower)
                    unique_ticks.add(tick_upper)

        # Fetch pool states for unique ticks within the range
        for tick in unique_ticks:
            tick_states[tick] = self.get_tick_state(tick)  # Fetch and store each tick state

        return tick_states

    
    def get_pool_state_for_all_positions(self):
        position_states = {}
        # Load all positions from the JSON file
        try:
            with open("model_storage/liq_positions.json", "r") as f:
                all_positions = json.load(f)
        except FileNotFoundError:
            print("No positions found.")
            return

        # Check if this pool_id exists in all_positions
        if self.pool_id not in all_positions:
            print(f"No positions found for pool {self.pool_id}.")
            return

        # Fetch positions for this specific pool
        for liquidity_provider_str, positions in all_positions[self.pool_id].items():
            for position in positions:
                tick_lower = position['tick_lower']
                tick_upper = position['tick_upper']
                liquidity = position['liquidity']
                position_key = f"{liquidity_provider_str}_{tick_lower}_{tick_upper}"
                position_states[position_key] = self.get_position_state(tick_lower, tick_upper,liquidity_provider_str)

        return position_states

    @enforce_types
    def Token1(self):
        token=self.token1
        return token

    @enforce_types
    def Token0(self):
        
        token=self.token0
        return token

    @enforce_types
    def Token1_address(self) -> str:
        return self.Token1().address

    @enforce_types
    def Token0_address(self) -> str:
        return self.Token0().address

    @enforce_types
    def fundToken1FromAbove(self,dst_address: str, amount_base: int):
        tx_receipt=self.Token1().transfer(dst_address, amount_base, txdict(GOD_ACCOUNT))
        print(f'funded account with token1: {tx_receipt.events}')

    @enforce_types
    def fundToken0FromAbove(self,dst_address: str, amount_base: int):
        tx_receipt=self.Token0().transfer(dst_address, amount_base, txdict(GOD_ACCOUNT))
        print(f'funded account with token0: {tx_receipt.events}')
        
    def budget_to_liquidity(self,tick_lower,tick_upper,usd_budget):
            
        q96 = 2**96
        def get_liquidity_for_amounts(sqrt_ratio_x96, sqrt_ratio_a_x96, sqrt_ratio_b_x96, amount0, amount1):
            if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
                sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96
            
            if sqrt_ratio_x96 <= sqrt_ratio_a_x96:
                return liquidity0(amount0, sqrt_ratio_a_x96, sqrt_ratio_b_x96)
            elif sqrt_ratio_x96 < sqrt_ratio_b_x96:
                liquidity0_value = liquidity0(amount0, sqrt_ratio_x96, sqrt_ratio_b_x96)
                liquidity1_value = liquidity1(amount1, sqrt_ratio_a_x96, sqrt_ratio_x96)
                return min(liquidity0_value, liquidity1_value)
            else:
                return liquidity1(amount1, sqrt_ratio_a_x96, sqrt_ratio_b_x96)

        def liquidity0(amount, pa, pb):
            if pa > pb:
                pa, pb = pb, pa
            return (amount * (pa * pb) / q96) / (pb - pa)

        def liquidity1(amount, pa, pb):
            if pa > pb:
                pa, pb = pb, pa
            return amount * q96 / (pb - pa)

        
        slot0_data = self.pool.slot0()
        sqrtp_cur =slot0_data[0]
        usdp_cur = sqrtp_to_price(sqrtp_cur)

        #amount_token0 =  ((0.5 * usd_budget)/usdp_cur) * eth
        #amount_token1 = 0.5 * usd_budget * eth

        sqrtp_low = tick_to_sqrtp(tick_lower)
        sqrtp_upp = tick_to_sqrtp(tick_upper)

        #'''
        # Allocate budget based on the current price
        if sqrtp_cur <= sqrtp_low:  # Current price is below the range
            # Allocate all budget to token0
            amount_token0 = usd_budget / usdp_cur  
            amount_token1 = 0
        elif sqrtp_cur >= sqrtp_upp:  # Current price is above the range
            # Allocate all budget to token1
            amount_token0 = 0
            amount_token1 = usd_budget 
        else:  # Current price is within the range
            # Calculate amounts for token0 and token1 using Eqs. 11 and 12 of eltas paper
            #amount_token0 = L * (sqrtp_upp - sqrtp_cur) / (sqrtp_cur * sqrtp_upp)
            #amount_token1 = L * (sqrtp_cur - sqrtp_low)
            def calculate_x_to_y_ratio(P, pa, pb):
                """Calculate the x to y ratio from given prices."""
                sqrtP = math.sqrt(P)
                sqrtpa = math.sqrt(pa)
                sqrtpb = math.sqrt(pb)
                return (sqrtpb - sqrtP) / (sqrtP * sqrtpb * (sqrtP - sqrtpa)) * P

            # Calculate the x_to_y_ratio
            x_to_y_ratio = calculate_x_to_y_ratio(P=sqrtp_to_price(sqrtp_cur), pa=tick_to_price(tick_lower), pb=tick_to_price(tick_upper))
            #print(f'ratio: {x_to_y_ratio}')
        
            budget_token0 = (usd_budget * x_to_y_ratio) / (1 + x_to_y_ratio)
            budget_token1 = usd_budget - budget_token0

            # Calculate the amount of token0 and token1 to be purchased with the allocated budget
            # Assuming token0 is priced at cur_price and token1 is the stablecoin priced at $1
            amount_token0 = budget_token0 / usdp_cur
            amount_token1 = budget_token1 

        # Convert amounts to the smallest unit of the tokens based on their decimals
        #print(f'amount0: {amount_token0}')
        #print(f'amount1: {amount_token1}')
        
        amount_token0 = toBase18(amount_token0)
        amount_token1 = toBase18(amount_token1)
        #'''
        
        liquidity=get_liquidity_for_amounts(sqrt_ratio_x96=sqrtp_cur, sqrt_ratio_a_x96=sqrtp_low, sqrt_ratio_b_x96=sqrtp_upp, amount0=amount_token0, amount1=amount_token1)
        
        return liquidity
    
    def budget_to_liquidity_single_sided(self,tick_lower,tick_upper,usd_budget):
            
        q96 = 2**96
        def get_liquidity_for_amounts(sqrt_ratio_x96, sqrt_ratio_a_x96, sqrt_ratio_b_x96, amount0, amount1):
            if sqrt_ratio_a_x96 > sqrt_ratio_b_x96:
                sqrt_ratio_a_x96, sqrt_ratio_b_x96 = sqrt_ratio_b_x96, sqrt_ratio_a_x96
            
            if sqrt_ratio_x96 <= sqrt_ratio_a_x96:
                return liquidity0(amount0, sqrt_ratio_a_x96, sqrt_ratio_b_x96)
            elif sqrt_ratio_x96 < sqrt_ratio_b_x96:
                liquidity0_value = liquidity0(amount0, sqrt_ratio_x96, sqrt_ratio_b_x96)
                liquidity1_value = liquidity1(amount1, sqrt_ratio_a_x96, sqrt_ratio_x96)
                return min(liquidity0_value, liquidity1_value)
            else:
                return liquidity1(amount1, sqrt_ratio_a_x96, sqrt_ratio_b_x96)

        def liquidity0(amount, pa, pb):
            if pa > pb:
                pa, pb = pb, pa
            return (amount * (pa * pb) / q96) / (pb - pa)

        def liquidity1(amount, pa, pb):
            if pa > pb:
                pa, pb = pb, pa
            return amount * q96 / (pb - pa)

        
        slot0_data = self.pool.slot0()
        sqrtp_cur =slot0_data[0]
        usdp_cur = sqrtp_to_price(sqrtp_cur)

        #amount_token0 =  ((0.5 * usd_budget)/usdp_cur) * eth
        #amount_token1 = 0.5 * usd_budget * eth

        sqrtp_low = tick_to_sqrtp(tick_lower)
        sqrtp_upp = tick_to_sqrtp(tick_upper)

        #'''
        # Allocate budget based on the current price
        if sqrtp_cur <= sqrtp_low:  # Current price is below the range
            # Allocate all budget to token0
            amount_token0 = usd_budget 
            amount_token1 = 0
        elif sqrtp_cur >= sqrtp_upp:  # Current price is above the range
            # Allocate all budget to token1
            amount_token0 = 0
            amount_token1 = usd_budget 
        else:  # Current price is within the range
            print('Not a single sided liquidty position')
            return
        amount_token0 = toBase18(amount_token0)
        amount_token1 = toBase18(amount_token1)
        #'''
        
        liquidity=get_liquidity_for_amounts(sqrt_ratio_x96=sqrtp_cur, sqrt_ratio_a_x96=sqrtp_low, sqrt_ratio_b_x96=sqrtp_upp, amount0=amount_token0, amount1=amount_token1)
        
        return liquidity


    def get_wallet_balances(self, recipient):
            recipient_address = recipient
            #print(f'{self.token0.symbol()}: {fromBase18(self.token0.balanceOf(recipient_address))}')
            #print(f'{self.token1.symbol()}: {fromBase18(self.token1.balanceOf(recipient_address))}')

            balances = {
            recipient_address: {
                'ETH': fromBase18(recipient.balance()),
                'token0': fromBase18(self.token0.balanceOf(recipient_address)),
                'token1': fromBase18(self.token1.balanceOf(recipient_address))
            }
        }
            return balances  