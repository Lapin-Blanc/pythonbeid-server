"""Generate the application .ico file from the tray icon drawing."""

from __future__ import annotations

from pathlib import Path

from eid_agent.tray import _create_icon_image

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    output_path = Path(__file__).parent / "eid-agent.ico"
    base_image = _create_icon_image(size=256)
    base_image.save(
        output_path,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
    )
    print(f"Icon written to {output_path}")


if __name__ == "__main__":
    main()
