import unittest
from unittest.mock import MagicMock, patch

import launcher


class SuggestedIpTests(unittest.TestCase):
    @patch("launcher.socket.socket")
    def test_prefers_private_address_selected_by_default_route(self, socket_factory):
        route_socket = MagicMock()
        route_socket.getsockname.return_value = ("192.168.2.65", 49152)
        socket_factory.return_value = route_socket

        self.assertEqual(launcher.suggested_ip(), "192.168.2.65")
        route_socket.connect.assert_called_once_with(("1.1.1.1", 443))
        route_socket.close.assert_called_once()

    @patch("launcher.socket.gethostbyname_ex")
    @patch("launcher.socket.socket")
    def test_ignores_public_looking_loopback_adapter(self, socket_factory, hostname_lookup):
        route_socket = MagicMock()
        route_socket.connect.side_effect = OSError("sem rota")
        socket_factory.return_value = route_socket
        hostname_lookup.return_value = (
            "servidor",
            [],
            ["54.232.189.113", "192.168.2.65"],
        )

        self.assertEqual(launcher.suggested_ip(), "192.168.2.65")
        route_socket.close.assert_called_once()

    @patch("launcher.socket.gethostbyname_ex")
    @patch("launcher.socket.socket")
    def test_falls_back_to_localhost_without_private_address(self, socket_factory, hostname_lookup):
        route_socket = MagicMock()
        route_socket.connect.side_effect = OSError("sem rota")
        socket_factory.return_value = route_socket
        hostname_lookup.return_value = ("servidor", [], ["54.232.189.113"])

        self.assertEqual(launcher.suggested_ip(), "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
