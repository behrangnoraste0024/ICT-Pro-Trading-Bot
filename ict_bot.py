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

        for swing in context.swings:

            flag = ""

            if swing.bos:
                flag = " <-- BOS"

            print(f"{swing}{flag}")

        print()
        print("===== BOS EVENTS =====")
        print()

        for bos in context.bos:
            print(bos)