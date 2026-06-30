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
