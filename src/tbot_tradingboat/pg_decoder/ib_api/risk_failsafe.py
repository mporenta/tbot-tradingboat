# -*- coding: utf-8 -*-

"""
RiskFailSafeObserver monitors the portfolio's daily unrealized P&L and closes all positions
if the P&L drops below the defined threshold (e.g., 1% loss).
"""
from loguru import logger
from datetime import datetime

class RiskFailSafeObserver:
    def __init__(self, loss_threshold: float = -1.0):
        """
        Initialize the risk fail-safe observer.
        
        :param loss_threshold: The percentage loss at which all positions should be closed.
        """
        self.loss_threshold = loss_threshold  # Default threshold: -1% daily loss
        self.start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.daily_pnl = 0.0

    def check_pnl(self, positions):
        """
        Check the combined unrealized P&L for all positions and close all positions if needed.
        
        :param positions: List of current portfolio positions.
        """
        total_unrealized_pnl = 0.0
        total_value = 0.0
        
        # Calculate total unrealized P&L and portfolio value
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
        if self.daily_pnl <= self.loss_threshold:
            return True
        return False

    def close_all_positions(self, positions):
        """
        Close all positions to minimize further losses.
        
        :param positions: List of current portfolio positions.
        """
        for position in positions:
            try:
                action = 'SELL' if position.position > 0 else 'BUY'
                contract = position.contract
                # Assuming position closing logic through an existing method
                # Replace with actual position closing logic using your framework.
                logger.info(f"Closing position for {contract.symbol} with action: {action}")
                # Example: self.ibsyn.placeOrder(contract, marketOrder(action, abs(position.position)))
            except Exception as e:
                logger.error(f"Failed to close position for {contract.symbol}: {e}")

    def update(self, caller=None, tbot_ts: str = "", data_dict: Dict = None, **kwargs):
        """
        Update method called by the TbotSubject to check P&L.
        """
        # Assuming `positions` is accessible from the calling framework.
        # Replace with actual method to fetch positions from your trading environment.
        positions = []  # Replace with actual positions fetch logic
        self.check_pnl(positions)

    def open(self):
        """
        Initialization method for the observer.
        """
        logger.info("RiskFailSafeObserver initialized.")

    def close(self):
        """
        Close method for the observer to handle cleanup.
        """
        logger.info("RiskFailSafeObserver closed.")
