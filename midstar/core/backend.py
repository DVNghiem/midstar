from abc import ABC, abstractmethod
from typing import Any
from redis.asyncio import Redis
import time

class StorageBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Any: ...

    @abstractmethod
    def increment(self, key, amount=1, expire=None):
        pass


class RedisBackend(StorageBackend):
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    def increment(self, key, amount=1, expire=None):
        """
        The `increment` function increments a value in Redis by a specified amount and optionally sets an
        expiration time for the key.

        :param key: The `key` parameter in the `increment` method is used to specify the key in the Redis
        database that you want to increment
        :param amount: The `amount` parameter in the `increment` method specifies the value by which the
        key's current value should be incremented. By default, it is set to 1, meaning that if no specific
        amount is provided, the key's value will be incremented by 1, defaults to 1 (optional)
        :param expire: The `expire` parameter in the `increment` method is used to specify the expiration
        time for the key in Redis. If a value is provided for `expire`, the key will expire after the
        specified number of seconds. If `expire` is not provided (i.e., it is `None`
        :return: The `increment` method returns the result of incrementing the value of the key by the
        specified amount. If an expiration time is provided, it also sets the expiration time for the key in
        Redis. The method returns the updated value of the key after the increment operation.
        """
        with self.redis.pipeline() as pipe:
            pipe.incr(key, amount)
            if expire:
                pipe.expire(key, int(expire))
            return pipe.execute()[0]

    def get(self, key):
        return int(self.redis.get(key) or 0)
    


class InMemoryBackend(StorageBackend):
    def __init__(self):
        self.storage = {}

    def increment(self, key, amount=1, expire=None):
        """
        The `increment` function updates the value associated with a key in a storage dictionary by a
        specified amount and optionally sets an expiration time.

        :param key: The `key` parameter in the `increment` method is used to identify the value that needs
        to be incremented in the storage. It serves as a unique identifier for the value being manipulated
        :param amount: The `amount` parameter in the `increment` method specifies the value by which the
        existing value associated with the given `key` should be incremented. By default, if no `amount` is
        provided, it will increment the value by 1, defaults to 1 (optional)
        :param expire: The `expire` parameter in the `increment` method is used to specify the expiration
        time for the key-value pair being incremented. If a value is provided for the `expire` parameter, it
        sets the expiration time for the key in the storage dictionary to the current time plus the
        specified expiration duration
        :return: The function `increment` returns the updated value of the key in the storage after
        incrementing it by the specified amount.
        """
        if key not in self.storage:
            self.storage[key] = {"value": 0, "expire": None}
        self.storage[key]["value"] += amount
        if expire:
            self.storage[key]["expire"] = time.time() + expire
        return self.storage[key]["value"]

    def get(self, key):
        """
        This Python function retrieves the value associated with a given key from a storage dictionary,
        checking for expiration before returning the value or 0 if the key is not found.

        :param key: The `key` parameter is used to specify the key of the item you want to retrieve from the
        storage. The function checks if the key exists in the storage dictionary and returns the
        corresponding value if it does. If the key has an expiration time set and it has expired, the
        function deletes the key
        :return: The `get` method returns the value associated with the given key if the key is present in
        the storage and has not expired. If the key is not found or has expired, it returns 0.
        """
        if key in self.storage:
            if self.storage[key]["expire"] and time.time() > self.storage[key]["expire"]:
                del self.storage[key]
                return 0
            return self.storage[key]["value"]
        return 0