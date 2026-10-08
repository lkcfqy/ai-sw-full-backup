"""Create visibly synthetic browser-upload fixtures, never real-model eval data."""

from pathlib import Path

from PIL import Image, ImageDraw


def main():
    output = Path(__file__).resolve().parents[1] / "test-results" / "ui"
    output.mkdir(parents=True, exist_ok=True)
    for number in (1, 2):
        image = Image.new("RGB", (1000, 720), "#f4f3e8")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 980, 700), outline="#547453", width=4)
        draw.text(
            (50, 45),
            f"SYNTHETIC UI ENGINEERING FIXTURE {number}",
            fill="#233420",
            font_size=32,
        )
        draw.text(
            (50, 88),
            "Not a real parts photo. Not AI accuracy evidence.",
            fill="#233420",
            font_size=22,
        )
        for cell in range(12):
            x = 50 + (cell % 4) * 230
            y = 160 + (cell // 4) * 165
            draw.rounded_rectangle(
                (x, y, x + 210, y + 140), radius=12, outline="#91aa82", width=3
            )
            draw.text((x + 12, y + 8), str(cell + 1), fill="#527642", font_size=22)
        image.save(output / f"SYNTHETIC_UI_FIXTURE_{number}.png")


if __name__ == "__main__":
    main()
