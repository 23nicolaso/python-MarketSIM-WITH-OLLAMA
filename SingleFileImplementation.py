import random
from langchain_ollama import OllamaLLM
import time
import math
import threading
import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import queue

# =========================== #
# Created by Nicolas Ollivier #
# Last Updated: 25-09-2024    #
# =========================== #

'''
Welcome to the codebase for OLLAMA Market Simulator!                                          
This codebase was designed to simulate a market in a fake world!                              
It is designed to be a simple simulation of how a market could react to random news events in short time periods.

Notes:                                                                                                  
 - ignore the fact that it was implemented in a single file, I just started coding it that way and then  
    it became too much effort to split up into multiple files.                                                                                                 
 - make sure you are running with Ollama open, as it is the model that powers the simulation.     
'''

model = OllamaLLM(model="llama3.1")

# =================================================== Data Structures ================================================================== #
accounts = {} # Stores list of Account objects, indexed by accountID
initial_prices = {"Simula 500":100, "Rivala ETF":100, "Allia ETF":100, "Factoria ETF":100, "Gold":4000} # Stores last price for each asset
last_prices = {"Simula 500":100, "Rivala ETF":100, "Allia ETF":100, "Factoria ETF":100, "Gold":4000} # Stores last price for each asset
spreads_by_market = {"Simula 500": 0.01, "Rivala ETF": 0.01, "Allia ETF": 0.01, "Factoria ETF": 0.01, "Gold": 0.5} # Stores the spread for each market
average_annual_return_by_market = {"Simula 500": 0.2, "Rivala ETF": 0.15, "Allia ETF": 0.12, "Factoria ETF": 0.09, "Gold": 0.05} # Stores the average annual return for each market
economic_health_by_market = {"Simula 500": 1, "Rivala ETF": 1, "Allia ETF": 1, "Factoria ETF": 1, "Gold": 1} # Stores the total economic health of each market
simulation_age = 0 # Stores the age of the simulation in total sets of 10 ticks note (treat 10 ticks as 1 minute)
price_history = {asset: [price] for asset, price in last_prices.items()} # Stores list of past prices for each asset
assets = ["Simula 500", "Rivala ETF", "Allia ETF", "Factoria ETF", "Gold"] # Stores list of assets
markets = {} # Stores list of OrderBook objects, indexed by asset
recentHeadlines = [] # Stores list of recently generated headlines
news_queue = queue.Queue()
chat_queue = queue.Queue()

current_asset = "Simula 500"
model_lock = threading.Lock()
# ====================================================================================================================================== #

# ============================================ Helper Functions ============================================ #
def update_price_history(asset, price):
    if asset in price_history:
        price_history[asset].append(price)
        if len(price_history[asset]) > 1000:
            price_history[asset] = price_history[asset][-1000:]
    else:
        price_history[asset] = [price]

def makeMarkets():
    for asset in assets:
        markets[asset] = OrderBook(asset, last_prices[asset])

def estimatePrice(asset):
    estimated_price = initial_prices[asset] * (1 + average_annual_return_by_market[asset] / 252 / 24) ** simulation_age
    economic_health_adjustment = economic_health_by_market[asset] * 100 * spreads_by_market[asset]
    adjusted_price = max(0,estimated_price + economic_health_adjustment)

    return adjusted_price

# ========================================================================================================== #

# ============================================ Class Definitions ============================================ #
class Account:
    def __init__(self, accountID, CASH):
        self.accountID = accountID
        self.positions = {"CASH": CASH}
    def addPosition(self, asset, quantity):
        if asset in self.positions:
            self.positions[asset] += quantity
        else:
            self.positions[asset] = quantity
    def getPosition(self, asset):
        return self.positions.get(asset, 0)
    def getCash(self):
        return self.positions["CASH"]
    def getValue(self):
        return self.positions["CASH"] + sum([self.positions[asset] * last_prices[asset] for asset in self.positions if asset != "CASH"])
    def tradeAtPrice(self, asset, price, quantity, direction):
        self.addPosition(asset, quantity*direction)
        self.addPosition("CASH", -price*quantity*direction)

class OrderBook:
    class OrderLevel:
        def __init__(self, price, quantity, asset, direction):
            self.asset = asset
            self.direction = 1 if direction == "buy" else -1
            self.price = price
            self.netQuantity = quantity
            self.orders = []
        def addOrder(self, quantity, accountID):
            self.netQuantity += quantity
            creation_time = time.time()
            self.orders.append([quantity, accountID, creation_time])
        def isEmpty(self):
            return self.netQuantity == 0
        def getPrice(self):
            return self.price
        def getQuantity(self):
            return self.netQuantity
        def fulfillAll(self):
            while self.orders:
                order = self.orders.pop(0)
                quantity, accountID, creation_time = order
                accounts[accountID].tradeAtPrice(self.asset, self.price, quantity, self.direction)
            
            self.netQuantity = 0
            last_prices[self.asset] = self.price 

        def cancelOldOrders(self):
            current_time = time.time()
            self.orders = [order for order in self.orders if current_time - order[2] < 100]
            self.netQuantity = sum([order[0] for order in self.orders])
        def cancelAll(self):
            self.orders = []
            self.netQuantity = 0

        def fulfillQuantity(self, quantityToFill):
            if quantityToFill >= self.netQuantity:
                quantityToFill -= self.netQuantity
                self.fulfillAll()
                return quantityToFill
            else:
                while quantityToFill > 0 and self.orders:
                    order = self.orders[0]
                    accountToModify = accounts[order[1]]

                    if quantityToFill >= order[0]:
                        # Full order needs to be fulfilled
                        accountToModify.tradeAtPrice(self.asset, self.price, order[0], self.direction)
                        quantityToFill -= order[0]
                        self.netQuantity -= order[0]
                        self.orders.pop(0)
                        last_prices[self.asset] = self.price
                    else:
                        # Order gets partially fulfilled
                        accountToModify.tradeAtPrice(self.asset, self.price, quantityToFill, self.direction)
                        order[0] -= quantityToFill
                        self.netQuantity -= quantityToFill
                        quantityToFill = 0
                        last_prices[self.asset] = self.price
                
                last_prices[self.asset] = self.price
                return 0
        def cancelOrdersFromID(self, accountID):
            new_orders = []
            for order in self.orders:
                if order[1] == accountID:
                    self.netQuantity -= order[0]
                else:
                    new_orders.append(order)
            self.orders = new_orders
            self.netQuantity = sum([order[0] for order in self.orders])

    def __init__(self, asset, initialPrice):
        self.asset = asset
        self.bids = {}
        self.asks = {}
        self.urgentBuys = []
        self.urgentSells = []
        last_prices[asset] = initialPrice

    def getBids(self):
        return self.bids
    def getAsks(self):
        return self.asks
    def getUrgentOrders(self):
        return self.urgentBuys, self.urgentSells

    def cancelAllOldOrders(self):
        for bid in self.bids.values():
            bid.cancelOldOrders()
        for ask in self.asks.values():
            ask.cancelOldOrders()
        self.clearEmptyOrderlevels()

    def display(self):
        print(f"{self.asset} Orderbook")
        print(f"Total Buy Orders: {len(self.bids)}")
        print(f"Total Sell Orders: {len(self.asks)}")
        print(f"Last Price: {self.getLastPrice()}")
        print(f"Bids: {[str(value.netQuantity) + ' at '  + str(value.price) for value in sorted(self.bids.values(), key=lambda x: x.price, reverse=True)]}")
        print(f"Asks: {[str(value.netQuantity) + ' at ' + str(value.price) for value in sorted(self.asks.values(), key=lambda x: x.price)]}")
        print(f"Bid Size: {self.getBidSize()}")
        print(f"Ask Size: {self.getAskSize()}")

    def displayPrice(self):
        print(f"{self.asset} price: {round(self.getLastPrice(), 2)}")

    def getBidSize(self):
        return sum([bid.netQuantity for bid in self.bids.values()])
    def getAskSize(self):
        return sum([ask.netQuantity for ask in self.asks.values()])

    def clearFarOrders(self):
        # To stop my computer from exploding, I clear orders that are too far away from the current price
        for bid in self.bids.values():
            if bid.price < self.getLastPrice() - 5:
                bid.cancelAll()

        for ask in self.asks.values():
            if ask.price > self.getLastPrice() + 5:
                ask.cancelAll()
        
        self.clearEmptyOrderlevels()

    def clearEmptyOrderlevels(self):
        bid_prices = list(self.bids.keys())
        ask_prices = list(self.asks.keys())
        
        while bid_prices:
            price = bid_prices.pop()
            if self.bids[price].netQuantity == 0:
                del self.bids[price]
        
        while ask_prices:
            price = ask_prices.pop()
            if self.asks[price].netQuantity == 0:
                del self.asks[price]

    def addOrder(self, direction, price, quantity, orderType, accountID):
        book = self.bids if direction == "buy" else self.asks
        if orderType=="limit":
            if price in book:
                book[price].addOrder(quantity, accountID)
            else:
                book[price] = self.OrderLevel(price, quantity, self.asset, 1 if direction == "buy" else -1)
                book[price].addOrder(quantity, accountID)
            self.matchBooks()
        else:
            # if self.asset == "Simula 500": # FOR DEBUGGING PURPOSES
            #     print(f"Urgent order: {quantity} at {price} by {accountID} with direction {direction}")

            if direction == "buy":
                self.urgentBuys.append((quantity, accountID))
            else:
                self.urgentSells.append((quantity, accountID))

            self.fillUrgentOrders()

    def getBestBid(self):
        if self.bids:
            return self.bids[max(self.bids.keys())]
        else:
            return None

    def getBestAsk(self):
        if self.asks:
            return self.asks[min(self.asks.keys())]
        else:
            return None

    def matchBooks(self):
        while True:
            bestBid = self.getBestBid()
            bestAsk = self.getBestAsk()
            if not bestBid or not bestAsk or bestBid.getPrice() < bestAsk.getPrice():
                break
            
            quantityToFill = min(bestBid.getQuantity(), bestAsk.getQuantity())
            bestBid.fulfillQuantity(quantityToFill)
            bestAsk.fulfillQuantity(quantityToFill)

            if bestBid.getQuantity() == 0:
                self.bids.pop(bestBid.getPrice())
            if bestAsk.getQuantity() == 0:
                self.asks.pop(bestAsk.getPrice())

    def getUnfilledUrgentOrders(self):
        return self.urgentBuys, self.urgentSells

    def fillUrgentOrders(self):
        filledOrders = 0
        # match buys and sells at the middle of the bid and ask
        while self.urgentBuys and self.urgentSells:
            sellAccountID = self.urgentSells[0][1]
            buyAccountID = self.urgentBuys[0][1]
            quantityFilled = min(self.urgentBuys[0][0], self.urgentSells[0][0])  
            filledOrders += quantityFilled
            
            if self.getBestBid() and self.getBestAsk():
                midPrice = (self.getBestBid().getPrice() + self.getBestAsk().getPrice()) / 2
            else:
                midPrice = self.getLastPrice()
            
            accounts[buyAccountID].addPosition(self.asset, quantityFilled)
            accounts[buyAccountID].addPosition("CASH", -midPrice*quantityFilled)
            accounts[sellAccountID].addPosition(self.asset, -quantityFilled)
            accounts[sellAccountID].addPosition("CASH", midPrice*quantityFilled)

            self.urgentBuys[0] = (self.urgentBuys[0][0] - quantityFilled, buyAccountID)
            self.urgentSells[0] = (self.urgentSells[0][0] - quantityFilled, sellAccountID)

            # Remove empty orders
            if self.urgentBuys[0][0] == 0:
                self.urgentBuys.pop(0)
            if self.urgentSells[0][0] == 0:
                self.urgentSells.pop(0)
            
            #print(4)
        
        # Fill remaining market orders against the order book
        while self.urgentBuys:
            filledOrders += self.urgentBuys[0][0]
            if self.urgentBuys[0][0] == 0:
                self.urgentBuys.pop(0)
            else:    
                buyAccountID = self.urgentBuys[0][1]
                if self.getBestAsk():
                    if self.getBestAsk().getQuantity() == 0:
                        self.asks.pop(self.getBestAsk().getPrice())
                    else:
                        quantityFilled = min(self.urgentBuys[0][0], self.getBestAsk().getQuantity())
                        self.getBestAsk().fulfillQuantity(quantityFilled)
                        self.urgentBuys[0] = (self.urgentBuys[0][0] - quantityFilled, buyAccountID)
                        accounts[buyAccountID].addPosition(self.asset, quantityFilled)
                        accounts[buyAccountID].addPosition("CASH", -self.getBestAsk().getPrice()*quantityFilled)
                        last_prices[self.asset] = self.getBestAsk().getPrice()
                else:
                    break
            
        #print(5)

        while self.urgentSells:
            filledOrders += self.urgentSells[0][0]
            if self.urgentSells[0][0] == 0:
                self.urgentSells.pop(0)
            else:
                sellAccountID = self.urgentSells[0][1]
                if self.getBestBid():
                    if self.getBestBid().getQuantity() == 0:
                        self.bids.pop(self.getBestBid().getPrice())
                    else:
                        quantityFilled = min(self.urgentSells[0][0], self.getBestBid().getQuantity())
                        self.getBestBid().fulfillQuantity(quantityFilled)
                        self.urgentSells[0] = (self.urgentSells[0][0] - quantityFilled, sellAccountID)
                        accounts[sellAccountID].addPosition(self.asset, -quantityFilled)
                        accounts[sellAccountID].addPosition("CASH", self.getBestBid().getPrice()*quantityFilled)
                        last_prices[self.asset] = self.getBestBid().getPrice()
                else:
                    break
        
        return filledOrders
        #print(6)
    def getLastPrice(self):
        return last_prices.get(self.asset, None)
# ============================================== Agent Classes ============================================== #
class MarketAgent:
    def __init__(self, accountID, cash):
        self.account = Account(accountID, cash)
        accounts[accountID] = self.account
        
    def placeOrder(self, orderBook, direction, price, quantity, orderType):
        orderBook.addOrder(direction, price, quantity, orderType, self.account.accountID)

    def displayAccount(self):
        print(f"Account {self.account.accountID} has {self.account.getCash()} cash and the following positions: {self.account.positions}")

class MarketMaker(MarketAgent):
    def __init__(self, accountID, cash, spreads):
        super().__init__(accountID, cash)
        self.spreads = spreads

    def wipeOldOrders(self, orderBook):
        value = orderBook.getLastPrice()

        for bidLevel in orderBook.bids.values():
            if value - bidLevel.getPrice() >= self.spreads[orderBook.asset] * 10:
                bidLevel.cancelOrdersFromID("MARKET MAKER")
        
        for askLevel in orderBook.asks.values():
            if askLevel.getPrice() - value >= self.spreads[orderBook.asset] * 10:
                askLevel.cancelOrdersFromID("MARKET MAKER")

    def wipeAllOrders(self, orderBook):
        for bidLevel in orderBook.bids.values():
            bidLevel.cancelOrdersFromID("MARKET MAKER")
        for askLevel in orderBook.asks.values():
            askLevel.cancelOrdersFromID("MARKET MAKER")

    def makeMarket(self, orderBook):
        midPrice = orderBook.getLastPrice()
        self.wipeAllOrders(orderBook)
        for i in range (1,10):
            bidPrice = round(midPrice - (self.spreads[orderBook.asset] / 2 * i), 2)
            self.placeOrder(orderBook, "buy", bidPrice, round(2**i), "limit")
        for i in range (1,10):
            askPrice = round(midPrice + (self.spreads[orderBook.asset] / 2 * i), 2)
            self.placeOrder(orderBook, "sell", askPrice, round(2**i), "limit")

    def provideLiquidity(self, orderBook):
        remaining_urgent_buys, remaining_urgent_sells = orderBook.getUnfilledUrgentOrders()
        
        for buyOrder in remaining_urgent_buys:
            self.placeOrder(orderBook, "sell", last_prices[orderBook.asset]+round(self.spreads[orderBook.asset]*buyOrder[0]/5, 2), buyOrder[0], "limit")
        
        for sellOrder in remaining_urgent_sells:
            self.placeOrder(orderBook, "buy", last_prices[orderBook.asset]-round(self.spreads[orderBook.asset]*sellOrder[0]/5, 2), sellOrder[0], "limit")
        
        orderBook.fillUrgentOrders()
        self.makeMarket(orderBook)

class ExecutionalTrader(MarketAgent):
    def __init__(self, accountID, cash):
        super().__init__(accountID, cash)
        self.intendedOrders = {}
        self.conditionalOrders = {}

    def getConditionalOrdersInDirection(self, orderBook, direction):
        if orderBook not in self.conditionalOrders:
            return 0
        orders = [order for order in self.conditionalOrders[orderBook] if order["direction"] == direction]
        return sum(order["quantity"] for order in orders)

    def placeConditionalOrder(self, orderBook, direction, price, quantity, priceCondition, conditionalDirection):
        if orderBook.asset not in self.conditionalOrders:
            self.conditionalOrders[orderBook.asset] = []
        self.conditionalOrders[orderBook.asset].append({"direction": direction, "price": price, "quantity": quantity, "priceCondition": priceCondition, "conditionalDirection": conditionalDirection})

    def checkConditionalOrders(self, ticker):
        if ticker not in self.conditionalOrders:
            return
        for order in self.conditionalOrders[ticker]:
            if (order["conditionalDirection"] == "above" and last_prices[ticker] >= order["priceCondition"]) or (order["conditionalDirection"] == "below" and last_prices[ticker] <= order["priceCondition"]):
                self.placeOrder(markets[ticker], order["direction"], order["price"], order["quantity"], "market")
                self.conditionalOrders[ticker].remove(order)

    def executeTradeInLegs(self, orderBook, direction, price, quantity):
        self.intendedOrders[orderBook] = {"direction": direction, "price": price, "quantity": quantity}
    
    def removeOldIntendedOrders(self):
        self.intendedOrders.clear()

    def partialExecuteMarket(self, orderBook):
        if random.random() < 0.05:
            if orderBook in self.intendedOrders:
                order = self.intendedOrders[orderBook]
                if order["quantity"] > 0:
                    # Determine a random amount to fill, between 0 and the full quantity
                    quantity_to_fill = random.randint(1, max(order["quantity"]//5,1))
                    
                    # Place the order
                    self.placeOrder(orderBook, order["direction"], order["price"], quantity_to_fill, "market")
                    
                    # Update the remaining quantity
                    order["quantity"] -= quantity_to_fill
                    
                    # commented out debug statement
                    # print(f"Partially executed {quantity_to_fill} out of {order['quantity'] + quantity_to_fill} for {orderBook.asset}")
                    
                    # If the order is completely filled, remove it from intended orders
                    if order["quantity"] <= 0:
                        del self.intendedOrders[orderBook]

    def updateOrdersInLegs(self, orderBook):
        if orderBook.getBestBid() is None or orderBook.getBestAsk() is None:
            return
        try:
            if self.intendedOrders[orderBook]["direction"] == "buy" and self.intendedOrders[orderBook]["price"] >= orderBook.getBestAsk().getPrice():
                quantityToFill = min(self.intendedOrders[orderBook]["quantity"],orderBook.getBestAsk().getQuantity())
                self.placeOrder(orderBook, "buy", 0, quantityToFill, "market")
                self.intendedOrders[orderBook]["quantity"] -= quantityToFill
            elif self.intendedOrders[orderBook]["direction"] == "sell" and self.intendedOrders[orderBook]["price"] <= orderBook.getBestBid().getPrice():
                quantityToFill = min(self.intendedOrders[orderBook]["quantity"],orderBook.getBestBid().getQuantity())
                self.placeOrder(orderBook, "sell", 0, quantityToFill, "market")
                self.intendedOrders[orderBook]["quantity"] -= quantityToFill
        except:
            return

class HedgeFund(ExecutionalTrader):
    def __init__(self, accountID, cash):
        super().__init__(accountID, cash)

class RetailTrader(MarketAgent):
    def __init__(self, accountID, cash):
        super().__init__(accountID, cash)
        self.retailSentimentScore = {"Simula 500": 0.5, "Rivala ETF": 0.5, "Allia ETF": 0.5, "Factoria ETF": 0.5, "Gold": 0.6} # Ranging from 0 to 1 (0 is very bearish, 1 is very bullish)
        self.newsUrgency = 1

    def estimateSentiment(self, orderBook):
        sentiment = self.retailSentimentScore[orderBook.asset]
        variation = random.uniform(-0.05, 0.05)  # Add a small random variation
        return max(0, min(1, sentiment + variation))  # Ensure the result is between 0 and 1
    
    def estimateImportance(self):
        importance = self.newsUrgency
        variation = random.randint(-2, 2)  # Add a small random variation
        return max(0, min(importance + variation, 10))

    def trade(self, orderBook):
        for _ in range(self.newsUrgency):
            try:
                sentiment = self.retailSentimentScore[orderBook.asset]
                bounded_sentiment = 0.3 + (0.4 * sentiment)  # Scale sentiment to be within 30%-70%
                direction = "buy" if bounded_sentiment > random.random() else "sell"
            except KeyError:
                direction = "buy" if random.random() < 0.6 else "sell"

            current_position = self.account.getPosition(orderBook.asset)

            if (direction == "buy" and current_position >= 10000) or (direction == "sell" and current_position <= -10000):
                continue  # Skip this trade if it would exceed position limits

            price = orderBook.getLastPrice()
            quantity = random.randint(1, 100)

            if 0.45 <= sentiment <= 0.55:
                estimated_price = estimatePrice(orderBook.asset)
                if random.random() < 0.7:  # 70% chance to head towards the estimated price
                    sentiment += random.uniform(0.1, 0.3) if price < estimated_price else random.uniform(-0.3, -0.1)
                else:  # 30% chance to shift to a random sentiment
                    sentiment += random.uniform(-0.2, 0.2)

            # Adjust quantity if it would exceed position limits
            if direction == "buy":
                quantity = min(quantity, 10000 - current_position)
            else:  # sell
                quantity = min(quantity, current_position + 10000)

            if quantity > 0:
                self.placeOrder(orderBook, direction, price, quantity, 'market')
    
    def setReversionUrgency(self, urgency):
        self.newsUrgency = urgency
        
    def shiftSentimentToMean(self):
        for asset in self.retailSentimentScore:
            current_sentiment = self.retailSentimentScore[asset]
            shift_amount = (0.55 - current_sentiment) / (100 * self.newsUrgency)
            self.retailSentimentScore[asset] += shift_amount
            
            # Ensure the sentiment stays within [0, 1] range
            self.retailSentimentScore[asset] = max(0, min(1, self.retailSentimentScore[asset]))

        if all(0.54 <= sentiment <= 0.56 for sentiment in self.retailSentimentScore.values()):
            self.newsUrgency = 1
# ========================================= End of Class Definitions ======================================== #

retailTrader = RetailTrader("RETAIL TRADER", 1000000)
hedgeFund = HedgeFund("HEDGE FUND", 5000000)
hftFund = HedgeFund("EVENTS TRADING FUND", 10000000)
TATraders = HedgeFund("TA Trading Firm", 1000000)
longTermInvestors = HedgeFund("Long Term Investors", 100000000000000)
mm = MarketMaker("MARKET MAKER", 100000000000000, spreads=spreads_by_market)

# make markets for the agents
makeMarkets()

# main loop
runSimulation = True
tick = 0

# Create the main window
root = tk.Tk()
root.title("Market Simulation")
root.geometry("2000x800")

# Create a frame for the dropdown and charts
frame = ttk.Frame(root)
frame.pack(fill=tk.BOTH, expand=True)

# Create the dropdown menu
asset_var = tk.StringVar()
asset_dropdown = ttk.Combobox(frame, textvariable=asset_var, values=assets)
asset_dropdown.set(assets[0])  # Set default value
asset_dropdown.grid(row=0,column=0,rowspan=1,columnspan=1)

# Create a number selection menu
chart_length_label = ttk.Label(frame, text="Chart Length")
chart_length_label.grid(row=0, column=1, rowspan=1, columnspan=1)

number_var = tk.IntVar(value=500)
number_spinbox = tk.Spinbox(frame, from_=1, to=1000, textvariable=number_var)
number_spinbox.grid(row=0, column=2, rowspan=1, columnspan=1)

# Create a figure for the chart
fig, ax = plt.subplots(figsize=(8, 6))
canvas = FigureCanvasTkAgg(fig, master=frame)
canvas_widget = canvas.get_tk_widget()
canvas_widget.grid(row=1,column=0,rowspan=3,columnspan=3)
# Create a text widget for the news feed
news_feed = tk.Text(frame, height=40, width=40)
news_feed.grid(row=1,column=3,rowspan=3,columnspan=1)
news_feed.insert(tk.END, "News Feed:\n")
news_feed.see(tk.END)  # Scroll to the bottom of the text widget


# Create a text widget for the news feed
chat_window = tk.Text(frame, height=40, width=40)
chat_window.grid(row=1,column=4,rowspan=3,columnspan=1)
chat_window.insert(tk.END, "Chat Window:\n")
chat_window.see(tk.END)  # Scroll to the bottom of the text widget

# Display all prices in real time
# Create a frame for the price table
price_frame = ttk.Frame(frame)
price_frame.grid(row=1, column=5, rowspan=1, columnspan=1, sticky="nsew")

# Create and set up the treeview for price display
price_tree = ttk.Treeview(price_frame, columns=("Asset", "Price"), show="headings")
price_tree.heading("Asset", text="Asset")
price_tree.heading("Price", text="Price")
price_tree.column("Asset", width=150, anchor="center")
price_tree.column("Price", width=150, anchor="center")
price_tree.pack(fill=tk.BOTH, expand=True)



# Function to update prices
def update_prices():
    for item in price_tree.get_children():
        price_tree.delete(item)
    for asset, price in last_prices.items():
        price_tree.insert("", "end", values=(asset, f"{price:.2f}"))

# Initial population of the price table
for asset, price in last_prices.items():
    price_tree.insert("", "end", values=(asset, f"{price:.2f}"))

# Start the price update loop
update_prices()


def update_charts():
    selected_asset = asset_var.get()
    
    # Update price history chart
    ax.clear()
    try:
        ax.plot(price_history[selected_asset][-number_var.get():])
    except:
        ax.plot(price_history[selected_asset][-200:])
    ax.set_title(f"{selected_asset} Price History")
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    canvas.draw()

def update_news_feed():
    try:
        while True:
            headline = news_queue.get_nowait()
            news_feed.insert(tk.END, f"{headline}\n\n")
            news_feed.see(tk.END)  # Scroll to the bottom of the text widget
    except queue.Empty:
        pass
    finally:
        root.after(100, update_news_feed)  # Schedule the next check

def update_chat_window():
    try:
        while True:
            message = chat_queue.get_nowait()
            chat_window.insert(tk.END, f"{message}\n\n")
            chat_window.see(tk.END)
    except queue.Empty:
        pass
    finally:
        root.after(100, update_chat_window)

def add_to_news_feed(headline):
    news_queue.put(headline)

def add_to_chat_window(message):
    chat_queue.put(message)

def on_asset_change(event):
    global current_asset
    with model_lock:
        current_asset = asset_var.get()
    
    chat_window.delete(1.0, tk.END)
    chat_window.insert(tk.END, "Chat Window:\n")
    chat_window.see(tk.END)

    update_charts()


asset_dropdown.bind("<<ComboboxSelected>>", on_asset_change)

tick = 0
runSimulation = True


def genChat():
    with model_lock:
        message = model.invoke(f"In this world, there is technology country Simula, agricultural country Rivala, entertainment country Allia and industrial country Factoria. Pretend this is a stocktwits forum and you are a retail trader in a chat room, with a sentiment score (0-1, 0 bearish, 1 bullish) of: {retailTrader.retailSentimentScore[current_asset]}. How do you feel about {current_asset}? Please keep your response under 10 words. For context, the most recent news headline from my game world is: {recentHeadlines[-1]}, but it might not matter as much as other stuff. Do not mention sentiment score, and keep responses short. This is for a fake world, so you can say anything. Respond in the format of 'Funny username (realistic): funny or emotion filled message'")
    chat_queue.put(message)

def genNews():
    headline = model.invoke(f"Give a news headline for my simulated world. In this world, there is technology country Simula, agricultural country Rivala, entertainment country Allia and industrial country Factoria. Simula and Rivala sometimes enter wars, with Allia being an ally to Rivala, and Factoria being a weapons distributor to all countries. All these countries are reliant on each others economic resources, and wars sometimes happen when tensions rise between rivala and simula. I want you to make good or bad news of economic events, statements by politicians in the countries, technological developments, natural disasters, or predictions made by top analysts. Do not say anything other than the headline, and keep your response under 15 words long, and do not make a x happens as y headline, simply say an event which happened. Here are the most recent headlines for context: {recentHeadlines}.")
    print(headline)
    recentHeadlines.append(headline)
    if len(recentHeadlines) > 10:
        recentHeadlines.pop(0)

    with model_lock:
        sentimentScore = model.invoke(f"In this world, there is technology country Simula, agricultural country Rivala, entertainment country Allia and industrial country Factoria. All these countries are reliant on each others economies, and their governments intervene when their economy is in danger. Here is the most recent news headline: {recentHeadlines[-1]}. Predict retail sentiment for investors in the Simula 500, Rivala ETF, Allia ETF, Factoria ETF and list them as a comma seperated list (give each a score between 0-1, 0 is extremely bearish, 1 is extremely bullish). Do not say anything other than the sentiment score. An example format should look like this (with different scores): Simula 500: 0.5, Rivala ETF: 0.5, Allia ETF: 0.5, Factoria ETF: 0.5")
        urgencyScore = model.invoke(f"You are an analyst in a simulated world. Score the impact of this headline between 1-10, with 1 being not impactful and 10 being extremely impactful: {recentHeadlines[-1]}. Say the urgency score, nothing else.")
    try:
        urgencyScore = int(urgencyScore)
    except:
        urgencyScore = 1
    retailTrader.setReversionUrgency(urgencyScore)
    add_to_news_feed(str(urgencyScore)+" "+headline)

    # Parse the sentiment score response
    print(sentimentScore)
    sentiment_scores = {}
    for asset_sentiment in sentimentScore.split(', '):
        try:
            asset, score = asset_sentiment.split(': ')
            sentiment_scores[asset] = float(score)
        except:
            print(f"Error parsing sentiment score: {asset_sentiment}")
    
    sentiment_scores["Gold"] = 0.7 + random.uniform(-0.3, 0.3)
    # Update retailTrader's sentiment dictionary
    # Ensure all assets have a sentiment score, defaulting to 0.5 if not set
    for asset in ["Simula 500", "Rivala ETF", "Allia ETF", "Factoria ETF", "Gold"]:
        if asset not in sentiment_scores:
            sentiment_scores[asset] = 0.5

    retailTrader.retailSentimentScore = sentiment_scores
    
    # Simulate HFT trading the news
    for market in assets:
        mm.makeMarket(markets[market])
        #  If sentiment is above 0.9 or below 0.1, make the HFT front run the trade by market buying/selling and then doing a smart execution to close
        if retailTrader.estimateSentiment(markets[market]) <= 0.25:
            try:
                current_price = markets[market].getLastPrice()
                bid = markets[market].getBestBid().price
            except:
                current_price = markets[market].getLastPrice()
                bid = markets[market].getLastPrice()
            quantity = 5*math.pow(max(1,retailTrader.estimateImportance()),3)
            if retailTrader.estimateImportance() >= 8:
                hftFund.executeTradeInLegs(markets[market], "sell", current_price, quantity)
            else:
                hftFund.placeOrder(markets[market], "sell", current_price, quantity, "market")
                mm.provideLiquidity(markets[market])
                hftFund.placeOrder(markets[market], 'buy', bid, math.floor(quantity/2), 'limit')
                hftFund.executeTradeInLegs(markets[market], "buy", bid, math.floor(quantity/2))
                mm.makeMarket(markets[market])
        elif retailTrader.estimateSentiment(markets[market]) >= 0.75:
            try:
                current_price = markets[market].getLastPrice()
                ask = markets[market].getBestAsk().price
            except:
                current_price = markets[market].getLastPrice()
                ask = markets[market].getLastPrice()
            quantity = 20*math.pow(max(1,retailTrader.estimateImportance()),3)
            if retailTrader.estimateImportance() >= 8:
                hftFund.executeTradeInLegs(markets[market], "buy", current_price, quantity)
            else:
                hftFund.placeOrder(markets[market], "buy", current_price, quantity, "market")
                mm.provideLiquidity(markets[market])
                hftFund.placeOrder(markets[market], 'sell', ask, math.floor(quantity/2), 'limit')
                hftFund.executeTradeInLegs(markets[market], "sell", ask, math.floor(quantity/2))
                mm.makeMarket(markets[market])
        else:
            current_price = markets[market].getLastPrice()
            expected_price = estimatePrice(market)
            price_difference = abs(current_price - expected_price) / expected_price

            if price_difference > 0.05:  # If the price is more than 5% away from the expected price
                quantity = 5 * math.pow(max(1, retailTrader.estimateImportance()), 3)
                if current_price > expected_price:
                    # Price is higher than expected, HFT should sell
                    hftFund.placeOrder(markets[market], "sell", current_price, quantity, "market")
                    mm.provideLiquidity(markets[market])
                    hftFund.placeOrder(markets[market], 'buy', current_price - 0.01, math.floor(quantity / 2), 'limit')
                    hftFund.executeTradeInLegs(markets[market], "buy", current_price - 0.01, math.floor(quantity / 2))
                else:
                    # Price is lower than expected, HFT should buy
                    hftFund.placeOrder(markets[market], "buy", current_price, quantity, "market")
                    mm.provideLiquidity(markets[market])
                    hftFund.placeOrder(markets[market], 'sell', current_price + 0.01, math.floor(quantity / 2), 'limit')
                    hftFund.executeTradeInLegs(markets[market], "sell", current_price + 0.01, math.floor(quantity / 2))
                mm.makeMarket(markets[market])

    # Adjust the economic health of each market based on the spread and the urgency of the news
    for market in assets:
        economic_health_by_market[market] += ((sentiment_scores[market]-0.5) * urgencyScore* urgencyScore) 
        print(market+": "+str(estimatePrice(market)))


    # markets[market].displayPrice()
    # print(hedgeFund.account.getValue())
        
genNews()
genChat()

def genNewsThread():
    threading.Thread(target=genNews, daemon=True).start()

def genChatThread():
    threading.Thread(target=genChat, daemon=True).start()
# Start the news feed update loop
root.after(100, update_news_feed)
root.after(100, update_chat_window)

def manageTATrades(market):
    # Calculate mean and standard deviation of price history
    price_list = price_history[market][-20:]
    mean_price = sum(price_list) / len(price_list)
    std_dev = (sum((x - mean_price) ** 2 for x in price_list) / len(price_list)) ** 0.5
    quantity = random.randint(1,100)
    current_price = markets[market].getLastPrice()

    # # # Position conditional orders at the high of the past 500 ticks and low of the past 500 ticks to emulate stop loss / take profit orders getting hit
    if len(price_history[market]) > 300:
        high = max(price_history[market][-300:])
        low = min(price_history[market][-300:]) 
    
        if TATraders.getConditionalOrdersInDirection(market, "sell") == 0 and TATraders.account.getPosition(market) > 0:
            TATraders.placeConditionalOrder(markets[market], "sell", low, TATraders.account.getPosition(market)//20, low, "below")
        elif TATraders.getConditionalOrdersInDirection(market, "buy") == 0 and TATraders.account.getPosition(market) < 0:
            TATraders.placeConditionalOrder(markets[market], "buy", high, -TATraders.account.getPosition(market)//20, high, "above")
   
    # Check if price moved over 1% in the past 8 ticks
    if len(price_list) >= 30:
        price_30_ticks_ago = price_list[-30]
        price_change = abs(current_price - price_30_ticks_ago) / price_30_ticks_ago
        price_5_ticks_ago = price_list[-5]

        if price_change > 0.01:
            # Add limit orders to calm down the move/push price back to average
            if current_price > price_30_ticks_ago:
                # Price increased, add sell limit orders
                TATraders.placeOrder(markets[market], "sell", price_5_ticks_ago, quantity * 10, "limit")
            else:
                # Price decreased, add buy limit orders
                TATraders.placeOrder(markets[market], "buy", price_5_ticks_ago, quantity * 10, "limit")


    # trade off 300 period moving average
    if len(price_list) > 300:
        ma_300 = sum(price_list[-300:]) / 300
        if current_price > ma_300:
            # Price is above 300 period MA, add sell limit orders
            TATraders.placeOrder(markets[market], "sell", current_price, quantity, "market")
        else:
            # Price is below 300 period MA, add buy limit orders
            TATraders.placeOrder(markets[market], "buy", current_price, quantity, "market")

    # Calculate 8-period moving average
    if len(price_list) >= 8:
        ma_8 = sum(price_list[-8:]) / 8
        
        # Determine action based on current price relative to 8-period MA
        if current_price < ma_8:
            # Sell market
            TATraders.placeOrder(markets[market], "sell", current_price, quantity, "market")
        else:
            # Buy market
            TATraders.placeOrder(markets[market], "buy", current_price, quantity, "market")
    
    if len(price_list) > 30:
        ma_30 = sum(price_list[-30:]) / 30
        if current_price < ma_30:
            # Sell market
            TATraders.placeOrder(markets[market], "sell", current_price, quantity, "market")
        else:
            # Buy market
            TATraders.placeOrder(markets[market], "buy", current_price, quantity, "market")

    # Limit the number of limitorders placed to save on compute
    max_orders = 20
    if len(markets[market].bids) + len(markets[market].asks) > max_orders:
        # Cancel all TA orders
        for bid_level in markets[market].bids.values():
            bid_level.cancelOrdersFromID("TA Trading Firm")
        for ask_level in markets[market].asks.values():
            ask_level.cancelOrdersFromID("TA Trading Firm")
        return

    # # place sell limit order at nearest vwap band above, and buy limit order at nearest vwap band below
    upper_band = std_dev * 3 + mean_price
    lower_band = std_dev * -3 + mean_price

    TATraders.placeOrder(markets[market], "sell", upper_band, quantity, "limit")
    TATraders.placeOrder(markets[market], "buy", lower_band, quantity, "limit")

    

while runSimulation:
    for market in assets:
        mm.makeMarket(markets[market])
        retailTrader.trade(markets[market])


    max_history_length = 1000
    for asset in price_history:
        if len(price_history[asset]) > max_history_length:
            price_history[asset] = price_history[asset][-max_history_length:]

    # hedgeFund.managePortfolio()
    retailTrader.shiftSentimentToMean()

    for market in assets:
        mm.provideLiquidity(markets[market])

    if tick > 10:        
        simulation_age += 1
        if random.random() < 0.01:
            genChatThread()
        if random.random() < 0.001:
            genNewsThread()
            # print("MM VALUE: " + str(mm.account.getValue()))
            # print("HFT FUND VALUE: " + str(hftFund.account.getValue()))
            # print("TA FUND VALUE: " + str(TATraders.account.getValue()))
            # print("RETAIL TRADER VALUE: " + str(retailTrader.account.getValue()))
    
        for market in assets:
            hftFund.partialExecuteMarket(markets[market])
            update_price_history(market, markets[market].getLastPrice())
            manageTATrades(market)
            TATraders.checkConditionalOrders(market)
            markets[market].clearEmptyOrderlevels()
            markets[market].cancelAllOldOrders()
            markets[market].clearFarOrders()

            # Fix pricing to be closer to the long term pricing estimate, using the long term investors
            avg_price = sum(price_history[market][-100:]) / 50
            estimated_fair_value = estimatePrice(market)
            # make the order sizes bigger the further price is away from fair value, with it starting from this point up to a max quantity of 10000
            position = longTermInvestors.account.getPosition(market)
            price = markets[market].getLastPrice()
            if price > estimated_fair_value:
                deviation = price - estimated_fair_value
                if deviation / estimated_fair_value >= 0.15:
                    quantity = min(int(deviation / estimated_fair_value * 10000), 5000)
                    longTermInvestors.placeOrder(markets[market], "sell", price, quantity, "market")
            elif price < estimated_fair_value:
                deviation = estimated_fair_value - price
                if deviation / estimated_fair_value >= 0.15:
                    quantity = min(int(deviation / estimated_fair_value * 10000), 5000)
                    longTermInvestors.placeOrder(markets[market], "buy", price, quantity, "market")

        update_charts()  # Update charts every 100 ticks
        update_prices()

        tick = 0
    
    root.update()  # Update the GUI
    
    tick += 1

root.mainloop()  # Start the GUI event loop