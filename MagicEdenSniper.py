import base58
import base64

import httpx

import json
from json.decoder import JSONDecodeError

import platform

from solana.keypair import Keypair
from solana.message import Message
from solana.publickey import PublicKey
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.transaction import  SIG_LENGTH
from solana.transaction import Transaction

import threading
import time


class Web3Client:

    @staticmethod
    def get_nft_data(
                mint_address, proxy,
                proxies = None):
        """Gets Token data for /buy_now"""
        
        while True:
            
            if proxy:
                proxy_data = proxy.split(':')
                proxies = {
                    'http://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1]),
                    'https://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1])
                }
            
            httpx_client = httpx.Client(http2 = True, proxies = proxies)

            try:
                response = httpx_client.get(
                    'https://api-mainnet.magiceden.io/rpc/getNFTByMintAddress/' + mint_address,
                    timeout = None
                ).json()
            except httpx.ProxyError:
                print('Proxy error - [Proxy: %s]' % (proxy))
                continue
            except (JSONDecodeError, TypeError):
                print('Rate limit(Get nft data) - [Proxy: %s; Message: Please update proxy list]' % (proxy))
                continue

            if not response.get('results'):
                continue
            
            nft_data = {
                "mintAddress": response['results']['mintAddress'],
                "owner": response['results']['owner'],
                "id": response['results']['id'],
                "price": response['results']['price'],
                "creators": response['results']['creators'],
                "title": response['results']['title']
            }
            
            if response['results'].get('escrowPubkey')\
            and response['results'].get('v2').get('auctionHouseKey')\
            and response['results'].get('v2').get('sellerReferral'):
                
                nft_data["escrowPubkey"] = response['results']['escrowPubkey']
                nft_data["auctionHouseKey"] = response['results']['v2']['auctionHouseKey']
                nft_data["sellerReferral"] = response['results']['v2']['sellerReferral']
                
            return nft_data

    @staticmethod
    def get_message(
                buyer, nft_data,
                proxy, proxies = None):
        """Gets Message from Magic Eden /buy_now. Old algoritm. Correct is: Serialized Transaction"""
        
        params = {
            "buyer": buyer,
            "seller": nft_data['owner'],
            "auctionHouseAddress": nft_data['auctionHouseKey'],
            "tokenMint": nft_data['mintAddress'],
            "tokenATA": nft_data['id'],
            "price": nft_data['price'],
            "sellerReferral": nft_data['sellerReferral'],
            "sellerExpiry": -1
        }
        
        headers = {
            'referer': 'https://magiceden.io/',
        }

        if proxy:
            proxy_data = proxy.split(':')       
            proxies = {
                'http://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1]),
                'https://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1])
            }
        
        httpx_client = httpx.Client(http2 = True, proxies = proxies)
        
        while True:
            try:
                message = httpx_client.get(
                    'https://api-mainnet.magiceden.io/v2/instructions/buy_now',
                    params = params,
                    headers = headers,
                    timeout = None
                ).json()        
                
                return message
            
            except httpx.ProxyError:
                print('Proxy error - [Proxy: %s]' % (proxy))
            except (JSONDecodeError, TypeError):
                print('Rate limit(Get message) - [Message: Please update proxy list]')

    @staticmethod
    def create_transaction(message):

        # Old Magic Eden message population
        
        # message = Message.deserialize(bytes(message['tx']['data']))
        # signatures = [base58.b58encode(bytes([1] * SIG_LENGTH))]
        
        # transaction = Transaction.populate(
        #     message,
        #     signatures
        # )
        
        transaction = Transaction.deserialize(bytes(message['txSigned']['data']))

        return transaction

    @staticmethod
    def send_transaction(
                transaction, rpc,
                signer, proxy,
                proxies = None):

        solana_client = Client(rpc)
        
        transaction.sign(signer)
        txn_wire = base64.b64encode(transaction.serialize())
        
        json = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [
                txn_wire.decode('utf8'),
                {
                    "encoding": "base64",
                    "commitment": "confirmed"
                }
            ]
        }

        if proxies is not None:
            proxy_data = proxy.split(':')
            proxies = {
                'http://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1]),
                'https://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1])
            }

        httpx_client = httpx.Client(http2 = True, proxies = proxies)

        try:
            rpc_response = httpx_client.post(
                rpc,
                json = json,
                timeout = None
            ).json()
        except httpx.ProxyError:
            print('Proxy error - [Proxy: %s]' % (proxy))
        except (JSONDecodeError, TypeError):
            print('Rate limit(Send transaction) - [Message: Please add more proxies or increase delay value]')
        
        return rpc_response

    @staticmethod
    def create_keypair(b58_key):
        keypair = Keypair.from_secret_key(base58.b58decode(b58_key))
        return keypair
            

class SniperThread:

    success = None

    def __init__(
                self, collection_name,
                rpc, roof,
                keypair, proxies):
        
        self.collection_name = collection_name
        self.rpc = rpc
        self.roof = roof
        self.keypair = keypair
        self.proxies = proxies

    def get_signatures(self, proxy, proxies = None):
        """Gets signatures from Magic Eden Program"""
                        
        json = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                "M2mx93ekt1fmXSVkTrUL9xVFHkmME8HTUi5Cyc5aF7K",
                {
                    "limit": 1000,
                    "commitment": "confirmed"
                }
            ]
        }

        if proxy:
            proxy_data = proxy.split(':')
            proxies = {
                'http://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1]),
                'https://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1])
            }

        httpx_client = httpx.Client(http2 = True, proxies = proxies)

        try:
            signatures = httpx_client.post(
                self.rpc,
                json = json,
                timeout = None
            ).json()['result']
        except httpx.ProxyError:
            print('Proxy error - [Proxy: %s]' % (proxy))
        except (JSONDecodeError, TypeError):
            print('Rate limit(Get signatures) - [Message: Please add more proxies or increase delay value]')

        current_signatures = list([x['signature'] for x in signatures])
            
        return set(current_signatures)

    def check_transaction(
                self, signature,
                proxy, proxies = None):
        """Checks if transaction hasn't errors and has NFT transfer."""
        
        json = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                "json"
            ]
        }

        if proxy:
            proxy_data = proxy.split(':')
            proxies = {
                'http://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1]),
                'https://' : 'http://%s:%s@%s:%s' % (proxy_data[2], proxy_data[3], proxy_data[0], proxy_data[1])
            }

        httpx_client = httpx.Client(http2 = True, proxies = proxies)
        
        while True:
            
            try:                
                transaction = httpx_client.post(
                    self.rpc,
                    json = json,
                    timeout = None
                ).json()
                time.sleep(5)
            except httpx.ProxyError:
                print('Proxy error - [Proxy: %s]' % (proxy))
                continue
            except (JSONDecodeError, TypeError):
                print('Rate limit(Check transaction) - [Message: Please add more proxies or increase delay value]')
                continue
                
            if transaction.get('result'):
                break

        if self.success:
            return
                
        if transaction.get('result').get('meta'):
            if 'err' in transaction['result']['meta']:
                if not transaction['result']['meta']['err']:
                    if transaction['result']['meta'].get('postTokenBalances')\
                    and len(transaction['result']['meta']['postTokenBalances']) != 0:
                        
                        mint = transaction['result']['meta']['postTokenBalances'][0]['mint']
                        
                        nft_data = self.parse_nft(mint, proxy)
                            
                        if nft_data:

                            rpc_response = self.get_rpc_response(nft_data, proxy)
                            self.success = self.check_rpc_response(rpc_response)

    def get_rpc_response(self, nft_data, proxy):
        
        message = Web3Client.get_message(
            self.keypair.public_key,
            nft_data,
            proxy
        )

        transaction = Web3Client.create_transaction(message)

        if self.success:
            return

        rpc_response = Web3Client.send_transaction(
            transaction,
            self.rpc,
            self.keypair,
            proxy
        )

        return rpc_response

    def parse_nft(self, mint_address, proxy):
            for i in range(50):
                
                nft_data = Web3Client.get_nft_data(
                    mint_address,
                    proxy
                )     
                if not nft_data:
                    continue

                print('New listing - [Mint address: %s; Token: %s]' % (mint_address, nft_data['title']))
                    
                if self.collection_name not in nft_data['title']:
                    break

                if nft_data.get('escrowPubkey'):
                    if nft_data['price'] <= self.roof:
                        
                            print('Minting - [Price: %s; Token: %s]' % (nft_data['price'], nft_data['title']))
                            
                            return nft_data
                        
                    break

    def parse_recent(self, delay, proxy_index = 0):

        current_signatures = self.get_signatures(self.proxies[proxy_index])
        
        while True:
            
            if self.success:
                break
                            
            if proxy_index >= len(self.proxies):
                    proxy_index = 0
                    
            signatures = self.get_signatures(
                self.proxies[proxy_index]
            )
            
            new_signatures = set(signatures) - current_signatures
            current_signatures |= new_signatures
            
            proxy_index += 1
            
            for signature in list(new_signatures):
                
                if proxy_index >= len(self.proxies):
                    proxy_index = 0
                    
                threading.Thread(
                    target = self.check_transaction,
                    args = (
                        signature,
                        self.proxies[proxy_index],
                    )
                ).start()
                
                proxy_index += 1
                time.sleep(delay)

    def check_rpc_response(self, rpc_response):
        
        print('Rpc response - [Result: %s]' % (json.dumps(rpc_response)))
        
        if type(rpc_response.get('result')) is str:
            return True
        

if __name__ == '__main__':

    # Sniper setup example
    
    keypair = Web3Client.create_keypair(
        b58_key = 'Phantom Wallet base58 private key'
    )
    
    Thread = SniperThread(
        
        collection_name = 'Collection name from Magic Eden',
        rpc = 'https://solana-api.projectserum.com',

        # Roof price in sol
        roof = 1,
        
        keypair = keypair,
        proxies = [
            'ip:port:login:password'
        ]
        
    )
    
    Thread.parse_recent(
        delay = 0.01
    )
