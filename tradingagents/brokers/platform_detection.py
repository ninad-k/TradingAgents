"""
Platform detection and MT5 availability checking.

Detects OS and MetaTrader5 library availability for informed setup.
"""

import sys
import platform
import logging

logger = logging.getLogger(__name__)


class PlatformInfo:
    """Detect platform and MT5 availability."""

    @staticmethod
    def get_os() -> str:
        """Get operating system."""
        return platform.system()

    @staticmethod
    def get_os_version() -> str:
        """Get OS version."""
        return platform.release()

    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows."""
        return platform.system() == "Windows"

    @staticmethod
    def is_linux() -> bool:
        """Check if running on Linux."""
        return platform.system() == "Linux"

    @staticmethod
    def is_macos() -> bool:
        """Check if running on macOS."""
        return platform.system() == "Darwin"

    @staticmethod
    def is_native_mt5_supported() -> bool:
        """Check if platform supports native MetaTrader5 library."""
        return PlatformInfo.is_windows() or PlatformInfo.is_linux()

    @staticmethod
    def has_mt5_library() -> bool:
        """Check if MetaTrader5 library is installed."""
        try:
            import MetaTrader5
            return True
        except ImportError:
            return False

    @staticmethod
    def get_platform_info() -> dict:
        """Get comprehensive platform information."""
        return {
            "os": PlatformInfo.get_os(),
            "os_version": PlatformInfo.get_os_version(),
            "python_version": platform.python_version(),
            "is_windows": PlatformInfo.is_windows(),
            "is_linux": PlatformInfo.is_linux(),
            "is_macos": PlatformInfo.is_macos(),
            "native_mt5_supported": PlatformInfo.is_native_mt5_supported(),
            "has_mt5_library": PlatformInfo.has_mt5_library(),
            "recommended_connector": PlatformInfo.recommend_connector(),
        }

    @staticmethod
    def recommend_connector() -> str:
        """Recommend connector based on platform."""
        if not PlatformInfo.is_native_mt5_supported():
            return "mock"  # Use mock on unsupported platforms

        if PlatformInfo.has_mt5_library():
            return "native"  # Use native if library available

        return "mock"  # Fallback to mock

    @staticmethod
    def print_setup_guide() -> None:
        """Print platform-specific setup guide."""
        info = PlatformInfo.get_platform_info()

        print("\n" + "="*80)
        print(" PLATFORM DETECTION & MT5 SETUP GUIDE")
        print("="*80)

        print(f"\n📊 YOUR SYSTEM")
        print(f"  OS:              {info['os']} {info['os_version']}")
        print(f"  Python:          {info['python_version']}")

        print(f"\n🔌 MT5 CONNECTIVITY")
        print(f"  Native MT5 Support:  {'✓ Yes' if info['native_mt5_supported'] else '✗ No'}")
        print(f"  MT5 Library Installed: {'✓ Yes' if info['has_mt5_library'] else '✗ No'}")

        print(f"\n💡 RECOMMENDATION")
        print(f"  Use: {info['recommended_connector'].upper()} connector")

        if info['os'] == "Darwin":  # macOS
            print(f"\n📌 macOS SETUP")
            print(f"  Native MetaTrader5 library is not available on macOS.")
            print(f"  ✓ Use mock connector for development and testing")
            print(f"  ✓ Options for real trading:")
            print(f"    1. Run Windows/Linux VM for MT5")
            print(f"    2. Use MT5 REST API (Phase D)")
            print(f"    3. Remote MT5 server via SSH tunnel")

        elif info['os'] == "Windows":
            print(f"\n📌 WINDOWS SETUP")
            if info['has_mt5_library']:
                print(f"  ✓ MetaTrader5 library already installed!")
                print(f"  → Ready to configure broker credentials")
            else:
                print(f"  Install MetaTrader5 library:")
                print(f"    $ pip install MetaTrader5")
                print(f"  Then configure credentials:")
                print(f"    connector = MT5Connector(")
                print(f"        login=YOUR_LOGIN,")
                print(f"        password='YOUR_PASSWORD',")
                print(f"        server='ICMarkets-Demo'")
                print(f"    )")

        elif info['os'] == "Linux":
            print(f"\n📌 LINUX SETUP")
            if info['has_mt5_library']:
                print(f"  ✓ MetaTrader5 library already installed!")
                print(f"  → Ready to configure broker credentials")
            else:
                print(f"  Install MetaTrader5 library:")
                print(f"    $ pip install MetaTrader5")
                print(f"  Note: May require MT5 terminal running via Wine/Proton")

        print(f"\n" + "="*80)


def main():
    """Run platform detection and print setup guide."""
    PlatformInfo.print_setup_guide()


if __name__ == "__main__":
    main()
