# poly-market-maker

Market maker keeper for the Polymarket CLOB.

## NOTE

This software is experimental and in active development.
Use at your own risk.

## Description

The keeper is an automated market maker for CLOB markets.
Places and cancels orders to keep open orders near the midpoint price according to one of two strategies.

## Requirements

- Python 3.10

## Setup

- Run `./install.sh` to set up the virtual environment and install depedencies.

- Create a `.env` file. See `.env.example`.

- Modify the entries in `config.env`.

- Modify the corresponding strategy config in `./config`, if desired.

## Usage

- Start the keeper with `./run-local.sh`.

### Usage with Docker

- To start the keeper with docker, run `docker compose up`.

## Config

The `config.env` file defines 3 environment variables:

- `CONDITION_ID`, the condition id of the market in hex string format.
- `STRATEGY`, the strategy to use, either "Bands" or "AMM" (case insensitive)
- `CONFIG`, the path to the strategy config file.

## Strategies

- [Amm](./docs/strategies/amm.md)
- [Bands](./docs/strategies/bands.md)

### Strategy Lifecycle

Every `sync_interval` (the default is 30s), the strategies do the following:

1. Fetch the current midpoint price from the CLOB
2. Compute expected orders.
3. Compare expected orders to open orders.
4. Compute open orders to cancel and new orders to place to achieve or approximate the expected orders.
5. Cancel orders.
6. Place new orders.

When the app receives a SIGTERM, all orders are cancelled and the app exits gracefully.

TODO:

X. how to clear a position

1. simulate the strategy
   a. migrate the sports data
   DONE. strategy stop loss and time up sale. try to use market order
1. scores fluctuate backwards sometimes
1. handle the game ending case, the score will be
1. 1 point scoring does not trigger an execute
1. need to have current game time. if have less than x seconds, only if the scores are within these many points do trades trigger. a good metrics is to calculate the change as a percentage of the difference between the scores of the two teams. if they are 10 points apart, 3 points chnage will bring to 30% change. very significant. only look at changes of a certain percentage above. in 4th quarter only look at percentage change that is greater than 30%. in 3 10%. dont look at one point change
1. have a game over flag
1. why does the thread number keep increasing?

Given that balacne has collateral token A and token B, the way to
clear your position after x seconds no matter what
for each balance change, keep track of the time stamp, clear position after the time stamp
last balance change

alternative have a stop loss or stop profit

score changes vs balance changed
at any point in time, only keep one type of tokens
score changed + balance > 0 = this means that last order was processed. update the stop loss or stop profit
score changed + balance = 0 = buy accordingly
score unchanged + balance > 0 = clear position based on stop profit or stop loss
score unchanged + balance = 0 = do nothing
balance increased: launch another thread that times out for a few second and place a clearing position against that balance change

so there are two states i have to worries

The three major variables are pending orders, balance, scores:

1. pending orders

if balance

OrderManager

mgr.cancel_orders
add orders to cancelling
-> get_order_book would return yes orders are being canceld in OwnOrderBook
initalize a thread to cancel order for each order
remove the orders from canelling list regardless if it's succeeded

OrderMannager actively update its own orders and balances by running get_ordres function talking to the polymarket client

if score changed, - place a buy order for x, in the meantime cached a sell order of the same size. - reflect in the balance y - place a sell order after a certain amount of time sell at the market or should i sell at limit, i should sell at limit of the bid - active order y == cancel this after certain amount of time

after placing a buy order, time stamp a cached fucntion this function will

1. clear position: use size = min(balance.size, prev_order.size), side = sell to clear position
2. cancel active orders

if favorable score change happen before the next time stamp hits, renew the time stamps and order size
if unfavorable score change happens before the next tiem stamp hits, consume the cached function. do the same algorithm on the other side

always try to sell
