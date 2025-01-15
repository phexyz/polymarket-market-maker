from web3 import Web3

# Initialize Web3
w3 = Web3()

# Replace these values
condition_id = "0xB84FF1DA4D1d290c608F150F891f459Ba3cd0fFb"
outcome_index = 0  # Use 0 for "Yes", 1 for "No", etc.

# Compute token ID
token_id = w3.keccak(
    w3.codec.encode_abi(["bytes32", "uint256"], [condition_id, outcome_index])
)
print("Token ID:", token_id.hex())
