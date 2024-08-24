# -*- coding: utf-8 -*-
"""
RiskFailSafeObserver monitors the portfolio's daily unrealized P&L and closes all positions
if the P&L drops below the defined threshold (e.g., 1% loss). It also includes a test mode
to automatically close the "NVDA" position 120 seconds after it's filled.
"""
from loguru import logger
from datetime import datetime
from ib_insync import IB, Position, MarketOrder
import threading  # Import threading to handle delayed execution

class RiskFailSafeObserver:
    def __init__(self, ibsyn: IB, loss_threshold: float = -1.0, test_mode: int = 0):
        """
        Initialize the risk fail-safe observer.

        :param ibsyn: Instance of IB for accessing positions and placing orders.
        :param loss_threshold: The percentage loss at which all positions should be closed.
        :param test_mode: Set to 1 to enable the test mode that closes "NVDA" 120 seconds after the fill.
        """
        self.ibsyn = ibsyn  # IB instance to access positions and place orders
        self.loss_threshold = loss_threshold  # Default threshold: -1% daily loss
        self.start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.daily_pnl = 0.0
        self.contract_pnl = []  # Track contract-specific PnL updates
        self.test_mode = test_mode  # Test mode flag
        self.nvda_timer = None  # Timer for NVDA position closure in test mode

        # Subscribe to relevant IB events
        self.install_event_handlers()

    def install_event_handlers(self):
        """
        Install event handlers to listen to IB events related to positions and P&L.
        """
        self.ibsyn.positionEvent += self.on_position_event
        self.ibsyn.orderStatusEvent += self.on_order_status_event

    def on_position_event(self, position: Position):
        """
        Handle position updates.
        """
        logger.debug(f"Position update: {position.contract.symbol}, Position: {position.position}, Avg Cost: {position.avgCost}")
        self.check_pnl()

    def on_order_status_event(self, trade):
        """
        Handle order status updates. In test mode, close "NVDA" position after 120 seconds.
        """
        if self.test_mode == 1 and trade.contract.symbol == "NVDA" and trade.orderStatus.status == "Filled":
            logger.info(f"Test mode enabled: NVDA position filled. Scheduling closure in 120 seconds.")
            # Start a timer to close the NVDA position after 120 seconds
            self.nvda_timer = threading.Timer(120, self.close_nvda_position)
            self.nvda_timer.start()

    def close_nvda_position(self):
        """
        Close the NVDA position after the delay (120 seconds).
        """
        positions = self.ibsyn.positions()  # Fetch all current positions
        for position in positions:
            if position.contract.symbol == "NVDA":
                try:
                    action = 'SELL' if position.position > 0 else 'BUY'
                    contract = position.contract
                    # Place a market order to close the NVDA position
                    order = MarketOrder(action, abs(position.position))
                    self.ibsyn.placeOrder(contract, order)
                    logger.info(f"Test mode: Closing NVDA position with action: {action}")
                except Exception as e:
                    logger.error(f"Failed to close NVDA position: {e}")
                break

    def check_pnl(self):
        """
        Check the combined unrealized P&L for all positions and close all positions if needed.
        """
        total_unrealized_pnl = 0.0
        total_value = 0.0

        # Access positions from IB instance
        positions = self.ibsyn.positions()  # Fetch all current positions from IB
        for position in positions:
            unrealized_pnl = (position.position * position.contract.multiplier *
                              (position.marketPrice - position.avgCost))
            total_value += position.marketPrice * abs(position.position)
            total_unrealized_pnl += unrealized_pnl
        
        if self._calculate_daily_loss(total_unrealized_pnl, total_value):
            logger.warning("Daily P&L down by 1% or more. Triggering closure of all positions.")
            self.close_all_positions(positions)

    def _calculate_daily_loss(self, unrealized_pnl, total_value):
        """
        Calculate if the daily unrealized P&L exceeds the loss threshold.
        
        :param unrealized_pnl: The combined unrealized P&L of all positions.
        :param total_value: The total value of all positions in the portfolio.
        :return: True if the daily loss exceeds the threshold, False otherwise.
        """
        if total_value == 0:  # Prevent division by zero
            return False

        self.daily_pnl = (unrealized_pnl / total_value) * 100
        logger.info(f"Current daily unrealized P&L: {self.daily_pnl}%")
        
        # Check if the daily loss exceeds the loss threshold
        return self.daily_pnl <= self.loss_threshold

    def close_all_positions(self, positions):
        """
        Close all positions to minimize further losses.
        
        :param positions: List of current portfolio positions.
        """
        for position in positions:
            try:
                action = 'SELL' if position.position > 0 else 'BUY'
                contract = position.contract
                # Place a market order to close the position
                order = MarketOrder(action, abs(position.position))
                self.ibsyn.placeOrder(contract, order)
                logger.info(f"Closing position for {contract.symbol} with action: {action}")
            except Exception as e:
                logger.error(f"Failed to close position for {contract.symbol}: {e}")

    def open(self):
        """
        Initialization method for the observer.
        """
        logger.info("RiskFailSafeObserver initialized.")

    def close(self):
        """
        Close method for the observer to handle cleanup.
        """
        if self.nvda_timer:
            self.nvda_timer.cancel()  # Stop the timer if it's still running
        logger.info("RiskFailSafeObserver closed.")
