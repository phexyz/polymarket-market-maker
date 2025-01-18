
        # Define the CSV filename
        csv_filename = f"game_data_{self.game_id}.csv"

        # Define the header for the CSV file
        header = [
            "Timestamp",
            "Scores",
            "Market",
            "Price0",
            "Price1",
            "Order Book Bids",
            "Order Book Asks",
        ]

        # Check if the CSV file already exists to avoid rewriting the header
        file_exists = False
        try:
            with open(csv_filename, "r"):
                file_exists = True
        except FileNotFoundError:
            pass

        # Open the CSV file in append mode
        with open(csv_filename, mode="a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=header)

            # Write the header if the file doesn't already exist
            if not file_exists:
                writer.writeheader()

            prev_scores_dict = {}

            # Continuous data collection
            while True:
                # Collect scores
                scores = self.driver.find_elements(By.CLASS_NAME, "Gamestrip__Score")
                scores_dict = {
                    f"Score {idx + 1}": score.text for idx, score in enumerate(scores)
                }
                if scores_dict == prev_scores_dict:
                    continue
                prev_scores_dict = scores_dict

                # Iterate over active markets and log data
                for mkt in self.active_markets:
                    price0 = self.clob_api.get_price(mkt.clobTokenIds[0])
                    price1 = self.clob_api.get_price(mkt.clobTokenIds[1])
                    orderBook = self.clob_api.client.get_order_book(mkt.clobTokenIds[0])

                    # Format bids and asks as strings
                    bids = [
                        {"price": bid.price, "size": bid.size} for bid in orderBook.bids
                    ]
                    asks = [
                        {"price": ask.price, "size": ask.size} for ask in orderBook.asks
                    ]

                    # Prepare the row of data to write
                    row = {
                        "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Scores": str(scores_dict),
                        "Market": mkt.slug,
                        "Price0": price0,
                        "Price1": price1,
                        "Order Book Bids": str(bids),
                        "Order Book Asks": str(asks),
                    }
                    writer.writerow(row)

                # Wait 0.5 seconds before the next iteration
                time.sleep(0.5)
