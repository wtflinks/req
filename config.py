from os import getenv


class Config:
    # Mongo
    MONGO_URI = getenv("MONGO_URI", "mongodb+srv://tharkihoobooji:tharkihoobooji@cluster0.0fob9oi.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    MONGO_DB = getenv("MONGO_DB", "req")

    API_ID    = int(getenv("API_ID", "24777493"))
    API_HASH  = getenv("API_HASH", "bf5a6381d07f045af4faeb46d7de36e5")

    BOT_TOKEN = getenv("BOT_TOKEN", "8769732364:AAGe91zu6I0mKEmV1KlqbQkGHyQl_dMstrM")

    SESSION   = getenv("SESSION","")
    
    SUDO      = list(map(int, getenv("SUDO", "7118393050 6992533662 8387324042").split()))
    
    FORCESUB  = getenv("FORCESUB", None)
    FSUB_CHAT_ID   = int(getenv("FSUB_CHAT_ID", 0))
    FSUB_CHAT_LINK = str(getenv("FSUB_CHAT_LINK", "0"))
    
    INLINE_BUTTON_LINK = getenv("INLINE_BUTTON_LINK", "https://t.me/")
 
cfg = Config()
