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
