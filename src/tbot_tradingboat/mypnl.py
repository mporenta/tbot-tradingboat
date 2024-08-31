import logging
from datetime import datetime
import pytz
from ib_insync import IB, MarketOrder

# Set up logging configuration at the start of the script
logging.basicConfig(
    level=logging.INFO,  # Set the logging level
    format='%(asctime)s [%(levelname)s] %(message)s',  # Set the log message format
    handlers=[
        logging.FileHandler("trading_strategy.log"),  # Log to a file
        logging.StreamHandler()  # Also log to the console
    ]
)

logging.info("Logging is configured.")

class SimplePnLStrategy:
    def __init__(self, host='127.0.0.1', port=4002, client_id=2, account_balance=1007812.0):
        self.host = host
        self.port = port
        self.client_id = client_id

        self.ib = None
        self.pnl = None
        self.account_balance = account_balance  # User-provided account balance
        self.loss_threshold = -0.01 * self.account_balance  # 1% of the account balance

        logging.info("SimplePnLStrategy initialized.")

    def setup_logging(self):
        # Setup logging configuration
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)  # Set the default logging level

        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

        file_handler = logging.FileHandler("trading_strategy.log")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        logger.info("Logger initialized.")

    def run(self):
        logging.info("Running the strategy...")

        # Establish connection to IB
        self.connect_to_ib()

        # Subscribe to order events
        self.subscribe_to_events()

        # Wait until there is at least one open position
        self.wait_for_initial_position()

        # Subscribe to PnL updates
        self.request_pnl_updates()

        logging.info("Entering main update loop...")

        # Enter the event-driven loop to monitor PnL updates
        self.ib.run()


    def get_current_time(self):
        local_tz = pytz.timezone('America/New_York')
        return datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')

    def connect_to_ib(self):
        try:
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logging.info("Connected to IB at %s", self.get_current_time())
        except Exception as e:
            logging.error("Failed to connect to IB: %s", str(e))

    def subscribe_to_events(self):
        self.ib.newOrderEvent += self.on_new_order
        logging.info("Subscribed to newOrderEvent.")

        self.ib.orderModifyEvent += self.on_order_modify
        logging.info("Subscribed to orderModifyEvent.")

        self.ib.cancelOrderEvent += self.on_cancel_order
        logging.info("Subscribed to cancelOrderEvent.")

        self.ib.openOrderEvent += self.on_open_order
        logging.info("Subscribed to openOrderEvent.")

        self.ib.orderStatusEvent += self.on_order_status
        logging.info("Subscribed to orderStatusEvent.")

        logging.info("All order events subscribed.")


    def on_new_order(self, trade):
        logging.info(f"New order placed: {trade}")

    def on_order_modify(self, trade):
        logging.info(f"Order modified: {trade}")

    def on_cancel_order(self, trade):
        logging.info(f"Order cancelled: {trade}")

    def on_open_order(self, trade):
        logging.info(f"Open order: {trade}")

    def on_order_status(self, trade):
        logging.info(f"Order status changed: {trade}")


    def wait_for_initial_position(self):
        logging.info("Waiting for initial position...")
        while not self.ib.positions():
            self.ib.sleep(1)
        logging.info("Initial position detected. Starting strategy.")

    def request_pnl_updates(self):
        try:
            account = self.ib.managedAccounts()[0]
            self.ib.reqPnL(account)
            self.ib.pnlEvent += self.on_pnl
            logging.info("Subscribed to PnL updates.")
        except Exception as e:
            logging.error("Failed to subscribe to PnL updates: %s", str(e))

    def on_pnl(self, pnl):
        self.pnl = pnl
        if pnl.avgCost == 0:
            logging.warning("Received PnL data with zero avgCost; skipping further processing for this contract.")
            return 
        logging.info(
            "PnL updated: Daily PnL: %.2f, Realized PnL: %.2f, Unrealized PnL: %.2f at %s",
            pnl.dailyPnL, pnl.realizedPnL, pnl.unrealizedPnL, self.get_current_time()
        )

        if self.check_loss_threshold():
            self.close_all_positions()
            logging.info("Loss threshold exceeded, positions closed. Exiting strategy.")
            self.ib.disconnect()

    def check_loss_threshold(self):
        if self.pnl and self.pnl.dailyPnL <= self.loss_threshold:
            logging.warning(
                "Loss threshold of %.2f (1%% of account balance) exceeded with daily PnL: %.2f at %s",
                self.loss_threshold, self.pnl.dailyPnL, self.get_current_time()
            )
            return True
        return False

    def close_all_positions(self):
        logging.info("Attempting to close all positions at %s", self.get_current_time())
        for position in self.ib.positions():
            contract = position.contract
            qty = position.position

            if qty > 0:
                order = MarketOrder('SELL', qty)
            elif qty < 0:
                order = MarketOrder('BUY', abs(qty))
            else:
                logging.info("No position to close for %s at %s", contract.symbol, self.get_current_time())
                continue

            logging.info("Placing order for %s to close position of %d units at %s", contract.symbol, qty, self.get_current_time())

            try:
                trade = self.ib.placeOrder(contract, order)
                logging.info("Placed order to close position for %s: %s at %s", contract.symbol, trade, self.get_current_time())
            except Exception as e:
                logging.error("Failed to place order for %s: %s", contract.symbol, str(e))

        logging.info("Completed position closing attempt at %s", self.get_current_time())



if __name__ == "__main__":
    logging.info("Script is starting...")
    # User can set their account balance here
    account_balance = 1007812.0  # Example: $100,000
    strategy = SimplePnLStrategy(account_balance=account_balance)
    strategy.run()
    logging.info("Script has finished.")
