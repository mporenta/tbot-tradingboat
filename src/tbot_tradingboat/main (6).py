import sys
import os
import socket
import dotenv
from dotenv import load_dotenv
import logging
import numpy as np
from ib_insync import *
import time
import threading

# Load environment variables from .env file
load_dotenv()

# Access environment variables
ibkr_addr = os.getenv("IBKR_ADDR", "localhost")
ibkr_port = int(os.getenv("IBKR_PORT", 4002))
ibkr_clientid = int(os.getenv("TBOT_IBKR_CLIENTID", 2))

# Configure logging
logging.basicConfig(level=os.getenv("TBOT_LOGLEVEL", "INFO"), format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Connect to Interactive Brokers
ib = IB()

# Global variables
positions_closed = False
positions_closed_lock = threading.Lock()

def is_port_open(host, port, timeout=1):
    """Check if the specified port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except socket.error:
            return False

def connect_to_ib(max_retries=10, delay=10):
    retries = 0
    while retries < max_retries:
        if is_port_open(ibkr_addr, ibkr_port):
            try:
                ib.connect(ibkr_addr, ibkr_port, clientId=ibkr_clientid)
                logger.info("From Close-All: Connected to IBKR successfully.")
                return True
            except Exception as e:
                retries += 1
                logger.error(f"From Close-All: Failed to connect to IBKR. Attempt {retries}/{max_retries}: {e}")
                time.sleep(delay)
        else:
            logger.error(f"From Close-All: Port {ibkr_port} on {ibkr_addr} is not open. Retrying...")
            retries += 1
            time.sleep(delay)

    logger.error("From Close-All: Failed to connect to IBKR after multiple attempts. Exiting...")
    sys.exit(1)

def set_initial_net_liq():
    global initial_net_liq
    try:
        account_summary = ib.accountSummary()
        initial_net_liq = float([item for item in account_summary if item.tag == 'NetLiquidation'][0].value)
        logger.info(f"From Close-All: Initial Net Liquidation Value set to {initial_net_liq}")
    except Exception as e:
        logger.error(f"From Close-All: Error setting initial net liquidation value: {e}")
        sys.exit(1)

def close_all_positions():
    global positions_closed
    with positions_closed_lock:
        if positions_closed:
            logger.info("From Close-All: Positions have already been closed. Skipping this action.")
            return

        positions = ib.positions()
        for position in positions:
            contract = position.contract
            quantity = position.position

            # If long position, sell it; if short position, buy to cover
            if quantity > 0:
                order = MarketOrder('SELL', quantity)
            else:
                order = MarketOrder('BUY', -quantity)

            try:
                trade = ib.placeOrder(contract, order)
                trade_status = ib.waitOnUpdate(timeout=10)  # Wait for the order to complete
                if trade.orderStatus.status == 'Filled':
                    logger.info(f"From Close-All: Successfully closed position in {contract.symbol}, Quantity: {quantity}")
                else:
                    logger.error(f"From Close-All: Order for {contract.symbol} did not complete in time.")
            except Exception as e:
                logger.error(f"From Close-All: Error placing order for {contract.symbol}: {e}")

        positions_closed = True
        logger.info("From Close-All: All positions have been closed.")

def close_nvda_position_with_test_logic():
    # Test logic for NVDA ticker
    positions = ib.positions()
    for position in positions:
        if position.contract.symbol == "NVDA":
            logger.info("From Test: NVDA position detected, executing test closure.")
            contract = position.contract
            quantity = position.position

            # Fetch the last price for NVDA
            ticker = ib.reqMktData(contract, '', False, False)
            ib.sleep(1)  # Allow time for price to be fetched
            while ticker.last is None:  # Wait until we get the last price
                ib.sleep(0.5)
            last_price = ticker.last

            # Ensure tick size is defined, else use a default value
            tick_size = contract.minTick or 0.01  # Default tick size if not provided
            if quantity > 0:
                # Long position, place sell limit order 2 ticks below last price
                limit_price = last_price - 2 * tick_size
                order = LimitOrder('SELL', quantity, limit_price)
            else:
                # Short position, place buy to cover limit order 2 ticks above last price
                limit_price = last_price + 2 * tick_size
                order = LimitOrder('BUY', -quantity, limit_price)

            # Place the limit order
            try:
                trade = ib.placeOrder(contract, order)
                logger.info(f"From Test: Placed limit order for NVDA, Quantity: {quantity}, Limit Price: {limit_price}")
                ib.sleep(10)  # Wait for 10 seconds to see if the order fills
                if trade.orderStatus.status == 'Filled':
                    logger.info("From Test: NVDA limit order filled.")
                else:
                    logger.info("From Test: NVDA limit order not filled, sending market order.")
                    # Send a market order to close the position
                    if quantity > 0:
                        market_order = MarketOrder('SELL', quantity)
                    else:
                        market_order = MarketOrder('BUY', -quantity)
                    ib.placeOrder(contract, market_order)
                    logger.info("From Test: NVDA market order placed to close position.")
            except Exception as e:
                logger.error(f"From Test: Error executing NVDA order: {e}")

# Triggered on order execution or trade events
def update_data_and_evaluate_risk():
    try:
        account_values = ib.accountValues()
        portfolio = ib.portfolio()
        positions = ib.positions()
        trades = ib.trades()
        executions = ib.executions()

        unrealized_pnl = sum(pnl.unrealizedPnL for pnl in ib.pnl())
        realized_pnl = sum(pnl.realizedPnL for pnl in ib.pnl())
        total_pnl = np.sum([unrealized_pnl, realized_pnl])

        logger.info(f"From Close-All: Total Unrealized PnL: {unrealized_pnl}")
        logger.info(f"From Close-All: Total Realized PnL: {realized_pnl}")
        logger.info(f"From Close-All: Total PnL for the day: {total_pnl}")

        if unrealized_pnl <= -0.01 * initial_net_liq and not positions_closed:
            logger.warning("From Close-All: Unrealized PnL loss exceeds 1%. Closing all positions.")
            close_all_positions()

    except Exception as e:
        logger.error(f"From Close-All: Error while updating data and evaluating risk: {e}")

def on_order_event(trade):
    update_data_and_evaluate_risk()

def on_position_event(position):
    update_data_and_evaluate_risk()

def on_pnl_update(pnl):
    update_data_and_evaluate_risk()

def main():
    # Connect to IBKR
    connect_to_ib()

    # Set the initial net liquidation value
    set_initial_net_liq()

    # Test logic for NVDA
    if TEST_MODE == 1:
        close_nvda_position_with_test_logic()

    # Subscribe to necessary events
    ib.orderStatusEvent += on_order_event
    ib.execDetailsEvent += on_order_event
    ib.positionEvent += on_position_event
    ib.pnlEvent += on_pnl_update

    try:
        ib.run()
    except KeyboardInterrupt:
        logger.info("From Close-All: Script interrupted by user. Closing connection.")
    finally:
        if ib.isConnected():
            ib.disconnect()
        logger.info("From Close-All: Disconnected from IBKR.")

if __name__ == "__main__":
    main()
