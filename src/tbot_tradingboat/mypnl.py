import sys
import logging
from loguru import logger
from datetime import datetime
import pytz
from ib_insync import IB, MarketOrder, util
from utils.tbot_env import shared # type: ignore


# Set up loguru logging configuration at the start of the script
logger.remove()  # Remove default handler to avoid duplicate logs
logger.add("trading_strategy.log", level="INFO", format="{time} {level} {message}")  # Log to a file
logger.add(sys.stderr, level="INFO")  # Also log to the console

logger.info("Logging is configured.")


class SimplePnLStrategy:
    def __init__(self, host='127.0.0.1', port=4002, client_id=2, account_balance=1007812.0):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib_enable_log(shared.ib_loglevel)

        self.ib = None
        self.pnl = None
        self.account_balance = account_balance  # User-provided account balance
        self.loss_threshold = -0.01 * self.account_balance  # 1% of the account balance

        logger.info("SimplePnLStrategy initialized.")

    def ib_enable_log(self, level=logging.ERROR):
        """Enables ib insync logging"""
        util.logToConsole(level)  

    def run(self):
        logger.info("Running the strategy...")

        # Establish connection to IB
        self.connect_to_ib()

        # Request all open orders asynchronously
        self.ib.reqAllOpenOrdersAsync()

        # Subscribe to order events
        self.subscribe_to_events()

        # Wait until there is at least one open position
        self.wait_for_initial_position()

        # Subscribe to PnL updates
        self.request_pnl_updates()

        logger.info("Entering main update loop...")

        # Enter the event-driven loop to monitor PnL updates
        self.ib.run()

    def get_current_time(self):
        local_tz = pytz.timezone('America/New_York')
        return datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')

    def connect_to_ib(self):
        try:
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info("Connected to IB at {}", self.get_current_time())
            logging.info("Connected to IB at {}", self.get_current_time())
        except Exception as e:
            logger.error("Failed to connect to IB: {}", str(e))
            logging.error("Failed to connect to IB: {}", str(e))

    def subscribe_to_events(self):
        self.ib.newOrderEvent += self.on_new_order
        logger.info("Subscribed to newOrderEvent.")

        self.ib.orderModifyEvent += self.on_order_modify
        logger.info("Subscribed to orderModifyEvent.")

        self.ib.cancelOrderEvent += self.on_cancel_order
        logger.info("Subscribed to cancelOrderEvent.")

        self.ib.openOrderEvent += self.on_open_order
        logger.info("Subscribed to openOrderEvent.")

        self.ib.orderStatusEvent += self.on_order_status
        logger.info("Subscribed to orderStatusEvent.")

        logger.info("All order events subscribed.")

    def on_new_order(self, trade):
        logger.info("New order placed: {}", trade)

    def on_order_modify(self, trade):
        logger.info("Order modified: {}", trade)

    def on_cancel_order(self, trade):
        logger.info("Order cancelled: {}", trade)

    def on_open_order(self, trade):
        logger.info("Open order: {}", trade)

    def on_order_status(self, trade):
        logger.info("Order status changed: {}", trade)

    def wait_for_initial_position(self):
        logger.info("Waiting for initial position...")
        while not self.ib.positions():
            self.ib.sleep(1)
        logger.info("Initial position detected. Starting strategy.")
        logging.info("Initial position detected. Starting strategy.")

    def request_pnl_updates(self):
        try:
            account = self.ib.managedAccounts()[0]
            self.ib.reqPnL(account)
            self.ib.pnlEvent += self.on_pnl
            logger.info("Subscribed to PnL updates.")
        except Exception as e:
            logger.error("Failed to subscribe to PnL updates: {}", str(e))
            logging.error("Failed to subscribe to PnL updates: {}", str(e))

    def on_pnl(self, pnl):
        self.pnl = pnl
        if pnl.avgCost == 0:
            logger.warning("Received PnL data with zero avgCost; skipping further processing for this contract.")
            return
        logger.info(
            "PnL updated: Daily PnL: {:.2f}, Realized PnL: {:.2f}, Unrealized PnL: {:.2f} at {}",
            pnl.dailyPnL, pnl.realizedPnL, pnl.unrealizedPnL, self.get_current_time()
        )

        if self.check_loss_threshold():
            self.close_all_positions()
            logger.info("Loss threshold exceeded, positions closed. Exiting strategy.")
            logging.info("Loss threshold exceeded, positions closed. Exiting strategy.")
            self.ib.disconnect()

    def check_loss_threshold(self):
        if self.pnl and self.pnl.dailyPnL <= self.loss_threshold:
            logger.warning(
                "Loss threshold of {:.2f} (1%% of account balance) exceeded with daily PnL: {:.2f} at {}",
                self.loss_threshold, self.pnl.dailyPnL, self.get_current_time()
            )
            return True
        return False

    def close_all_positions(self):
        logger.info("Attempting to close all positions at {}", self.get_current_time())
        for position in self.ib.positions():
            contract = position.contract
            qty = position.position

            if qty > 0:
                order = MarketOrder('SELL', qty)
            elif qty < 0:
                order = MarketOrder('BUY', abs(qty))
            else:
                logger.info("No position to close for {} at {}", contract.symbol, self.get_current_time())
                continue

            logger.info("Placing order for {} to close position of {} units at {}", contract.symbol, qty, self.get_current_time())

            try:
                trade = self.ib.placeOrder(contract, order)
                logger.info("Placed order to close position for {}: {} at {}", contract.symbol, trade, self.get_current_time())
            except Exception as e:
                logger.error("Failed to place order for {}: {}", contract.symbol, str(e))

        logger.info("Completed position closing attempt at {}", self.get_current_time())


if __name__ == "__main__":
    logger.info("Script is starting...")
    # User can set their account balance here
    account_balance = 1007812.0  # Example: $100,000
    strategy = SimplePnLStrategy(account_balance=account_balance)
    strategy.run()
    logger.info("Script has finished.")
    logging.info("Script has finished.")
