import plotly.graph_objects as go
import plotly.io as pio

pio.renderers.default = "browser"


class ChartPlotter:

    def plot(self, df, swing_highs=None, swing_lows=None):

        fig = go.Figure()

        # کندل‌ها
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="BTCUSDT"
            )
        )

        # Swing High
        if swing_highs:

            fig.add_trace(
                go.Scatter(
                    x=[p[0] for p in swing_highs],
                    y=[p[1] for p in swing_highs],
                    mode="markers",
                    marker=dict(size=10, symbol="triangle-up"),
                    name="Swing High"
                )
            )

        # Swing Low
        if swing_lows:

            fig.add_trace(
                go.Scatter(
                    x=[p[0] for p in swing_lows],
                    y=[p[1] for p in swing_lows],
                    mode="markers",
                    marker=dict(size=10, symbol="triangle-down"),
                    name="Swing Low"
                )
            )

        fig.update_layout(
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            title="ICT Trading Bot"
        )

        fig.show()