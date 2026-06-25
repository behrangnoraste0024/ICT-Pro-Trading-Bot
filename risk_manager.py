class RiskManager:

    def calculate_position_size(self, capital, risk_percent, stop_loss):

        risk_amount = capital * (risk_percent / 100)

        position_size = risk_amount / stop_loss

        return position_size