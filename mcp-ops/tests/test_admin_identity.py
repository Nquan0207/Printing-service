import unittest
from unittest.mock import AsyncMock

from stockroom_ops.api import ApiError
from stockroom_ops.server import verify_ops_identity


class AdminIdentityGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_verifies_both_values(self) -> None:
        api = AsyncMock()

        result = await verify_ops_identity(api, "admin", "admin@gmail.com")

        self.assertIsNone(result)
        api.verify_admin_identity.assert_awaited_once_with("admin", "admin@gmail.com")

    async def test_backend_refusal_is_returned(self) -> None:
        api = AsyncMock()
        api.verify_admin_identity.side_effect = ApiError(403, "forbidden", "mismatch")

        result = await verify_ops_identity(api, "wrong", "admin@gmail.com")

        self.assertEqual(result["error"]["code"], "forbidden")


if __name__ == "__main__":
    unittest.main()
