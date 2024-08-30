import logging
from datetime import datetime
import pytz
from ib_insync import IB, MarketOrder

class SimplePnLStrategy:
    def __init__(self, host='127.0.0.1', port=4002, client_id=2, account_balance=1007812.0):
        self.host = host
        self.port = port
        self.client_id = client_id

        self.ib = None
        self.pnl = None
        self.account_balance = account_balance
        self.loss_threshold = -0.01 * self.account_balance
        self.is_running = False

        self.logger = logging.getLogger('SimplePnLStrategy')
        self.logger.info("SimplePnLStrategy initialized.")

    def start(self):
        self.connect_to_ib()
        self.subscribe_to_events()
        self.logger.info("SimplePnLStrategy started. Waiting for initial position.")

    def wait_for_initial_position(self):
        self.logger.info("Waiting for initial position...")
        while not self.ib.positions():
            self.ib.sleep(1)
        self.logger.info("Initial position detected. Starting PnL monitoring.")
        self.request_pnl_updates()
        self.is_running = True

    def process_ib_events(self):
        if not self.is_running and self.ib.positions():
            self.wait_for_initial_position()
        self.ib.sleep(0)  # Process IB events without blocking

    def get_current_time(self):
        local_tz = pytz.timezone('America/New_York')
        return datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')

    def connect_to_ib(self):
        try:
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id)
            self.logger.info("Connected to IB at %s", self.get_current_time())
        except Exception as e:
            self.logger.error("Failed to connect to IB: %s", str(e))

    def subscribe_to_events(self):
        self.ib.newOrderEvent += self.on_new_order
        self.ib.orderModifyEvent += self.on_order_modify
        self.ib.cancelOrderEvent += self.on_cancel_order
        self.ib.openOrderEvent += self.on_open_order
        self.ib.orderStatusEvent += self.on_order_status
        self.logger.info("All order events subscribed.")

    def on_new_order(self, trade):
        self.logger.info(f"New order placed: {trade}")

    def on_order_modify(self, trade):
        self.logger.info(f"Order modified: {trade}")

    def on_cancel_order(self, trade):
        self.logger.info(f"Order cancelled: {trade}")

    def on_open_order(self, trade):
        self.logger.info(f"Open order: {trade}")

    def on_order_status(self, trade):
        self.logger.info(f"Order status changed: {trade}")

    def request_pnl_updates(self):
        try:
            account = self.ib.managedAccounts()[0]
            self.ib.reqPnL(account)
            self.ib.pnlEvent += self.on_pnl
            self.logger.info("Subscribed to PnL updates.")
        except Exception as e:
            self.logger.error("Failed to subscribe to PnL updates: %s", str(e))

    def on_pnl(self, pnl):
        self.pnl = pnl
        self.logger.info(
            "PnL updated: Daily PnL: %.2f, Realized PnL: %.2f, Unrealized PnL: %.2f at %s",
            pnl.dailyPnL, pnl.realizedPnL, pnl.unrealizedPnL, self.get_current_time()
        )

        if self.check_loss_threshold():
            self.close_all_positions()
            self.logger.info("Loss threshold exceeded, positions closed. Exiting strategy.")
            self.stop()

    def check_loss_threshold(self):
        if self.pnl and self.pnl.dailyPnL <= self.loss_threshold:
            self.logger.warning(
                "Loss threshold of %.2f (1%% of account balance) exceeded with daily PnL: %.2f at %s",
                self.loss_threshold, self.pnl.dailyPnL, self.get_current_time()
            )
            return True
        return False

    def close_all_positions(self):
        self.logger.info("Attempting to close all positions at %s", self.get_current_time())
        for position in self.ib.positions():
            contract = position.contract
            qty = position.position

            if qty > 0:
                order = MarketOrder('SELL', qty)
            elif qty < 0:
                order = MarketOrder('BUY', abs(qty))
            else:
                self.logger.info("No position to close for %s at %s", contract.symbol, self.get_current_time())
                continue

            self.logger.info("Placing order for %s to close position of %d units at %s", contract.symbol, qty, self.get_current_time())

            try:
                trade = self.ib.placeOrder(contract, order)
                self.logger.info("Placed order to close position for %s: %s at %s", contract.symbol, trade, self.get_current_time())
            except Exception as e:
                self.logger.error("Failed to place order for %s: %s", contract.symbol, str(e))

        self.logger.info("Completed position closing attempt at %s", self.get_current_time())

    def stop(self):
        self.is_running = False
        if self.ib:
            self.ib.disconnect()
        self.logger.info("SimplePnLStrategy stopped.")
