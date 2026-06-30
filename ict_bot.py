from data.data_loader import DataLoader
from engine.ict_engine import ICTEngine


class ICTBot:

    def __init__(self):
        self.loader = DataLoader()
        self.engine = ICTEngine()

    def run(self):

        print("========== ICT BOT ==========\n")

        # دریافت داده‌ها
        df = self.loader.load_data()

        print(f"Candles Loaded : {len(df)}")

        # تحلیل بازار
        context = self.engine.analyze(df)

        print(f"Swings Found : {len(context.swings)}")

        print()
        print(f"Trend : {context.trend}")
        print(f"External High : {context.external_high}")
        print(f"External Low  : {context.external_low}")

        print()
        print("===== MARKET STRUCTURE =====")
        print()

        for event in context.structure:

            flag = ""

            if event.bos:
                flag = " <-- BOS"
            elif event.choch:
                flag = " <-- CHOCH"

            print(f"{event}{flag}")

        print()
        print("===== BOS EVENTS =====")
        print()

        for bos in context.bos:
            print(bos)

        print()
        print("===== CHOCH EVENTS =====")
        print()

        for choch in context.choch:
            print(choch)

        print()
        print("===== LIQUIDITY SWEEPS =====")
        print()

        for sweep in context.liquidity_sweeps:
            print(sweep)

        print()
        print("===== FAIR VALUE GAPS =====")
        print()

        for fvg in context.fvgs:
            print(fvg)

        print()
        print("===== ORDER BLOCKS =====")
        print()

        for order_block in context.order_blocks:
            print(order_block)

        print()
        print("===== BREAKER BLOCKS =====")
        print()

        for breaker_block in context.breaker_blocks:
            print(breaker_block)

        print()
        print("===== PREMIUM / DISCOUNT =====")
        print()

        print(f"Dealing Range High : {context.dealing_range_high}")
        print(f"Dealing Range Low  : {context.dealing_range_low}")
        print(f"Equilibrium        : {context.equilibrium}")
        print(f"Current Price      : {context.current_price}")
        print(f"Current Zone       : {context.current_price_zone}")

        print()
        print("===== OTE =====")
        print()

        if context.ote:
            print(f"OTE Direction : {context.ote_direction}")
            print(f"OTE Lower     : {context.ote_lower_bound}")
            print(f"OTE Upper     : {context.ote_upper_bound}")
            print(f"OTE 0.62      : {context.ote_level_62}")
            print(f"OTE 0.705     : {context.ote_level_705}")
            print(f"OTE 0.79      : {context.ote_level_79}")
            print(f"In OTE Zone  : {context.in_ote_zone}")
        else:
            print("OTE Direction : NONE")
            print("In OTE Zone  : False")

        print()
        print("===== SETUP =====")
        print()

        print(f"Setup Status : {context.setup_status}")
        print(f"Setup Bias   : {context.setup_bias}")
        print(f"Setup Score  : {context.setup_score}")
        print(f"Blockers     : {context.setup_blockers}")

        if context.active_setup:
            print(context.active_setup)

        print()
        print("===== ENTRY TRIGGER =====")
        print()

        print(f"Entry Status  : {context.entry_status}")
        print(f"Entry Direction: {context.entry_direction}")
        print(f"Trigger Type  : {context.entry_trigger_type}")
        print(f"Confirmed     : {context.entry_confirmed}")
        print(f"Blockers      : {context.entry_blockers}")

        if context.entry_trigger:
            print(context.entry_trigger)

        print()
        print("===== TRADE PLAN =====")
        print()

        print(f"Trade Plan Status : {context.trade_plan_status}")
        print(f"Trade Direction   : {context.trade_direction}")
        print(f"Entry Price       : {context.planned_entry_price}")
        print(f"Stop Loss         : {context.planned_stop_loss}")
        print(f"Take Profit       : {context.planned_take_profit}")
        print(f"Risk              : {context.planned_risk}")
        print(f"Reward            : {context.planned_reward}")
        print(f"Risk Reward       : {context.planned_risk_reward}")
        print(f"Blockers          : {context.trade_plan_blockers}")

        if context.trade_plan:
            print(context.trade_plan)

        print()
        print("===== TRADE QUALITY =====")
        print()

        print(f"Quality Status : {context.trade_quality_status}")
        print(f"Quality Score  : {context.trade_quality_score}")
        print(f"Reasons        : {context.trade_quality_reasons}")
        print(f"Blockers       : {context.trade_quality_blockers}")

        if context.trade_quality:
            print(context.trade_quality)

        print()
        print("===== PAPER TRADE =====")
        print()

        print(f"Paper Status    : {context.paper_trade_status}")
        print(f"Paper Direction : {context.paper_trade_direction}")
        print(f"Entry Price     : {context.paper_entry_price}")
        print(f"Stop Loss       : {context.paper_stop_loss}")
        print(f"Take Profit     : {context.paper_take_profit}")
        print(f"Entry Index     : {context.paper_entry_index}")
        print(f"Exit Price      : {context.paper_exit_price}")
        print(f"Exit Index      : {context.paper_exit_index}")
        print(f"Paper PnL       : {context.paper_pnl}")
        print(f"Reasons         : {context.paper_trade_reasons}")
        print(f"Blockers        : {context.paper_trade_blockers}")

        if context.paper_trade:
            print(context.paper_trade)

        print()
        print("===== BACKTEST =====")
        print()

        print(f"Total Trades    : {context.backtest_total_trades}")
        print(f"Closed Trades   : {context.backtest_closed_trades}")
        print(f"Open Trades     : {context.backtest_open_trades}")
        print(f"Wins            : {context.backtest_wins}")
        print(f"Losses          : {context.backtest_losses}")
        print(f"Win Rate        : {context.backtest_win_rate}")
        print(f"Net PnL         : {context.backtest_net_pnl}")
        print(f"Average PnL     : {context.backtest_average_pnl}")
        print(f"Max Drawdown    : {context.backtest_max_drawdown}")
        print(f"Ignored Contexts: {context.backtest_ignored_contexts}")

        if context.backtest_result:
            print(context.backtest_result)

        print()
        print("===== ROLLING BACKTEST =====")
        print()
        print("Rolling Backtest : available via RollingBacktestEngine")
        print("Default main.py does not run rolling backtest automatically.")
