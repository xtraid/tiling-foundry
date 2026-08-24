import argparse
from classes import RenderingPipeline


def main():
    parser = argparse.ArgumentParser(description="PAP pixel art renderer")
    parser.add_argument("palette", help="path to palette.json")
    parser.add_argument("scene", help="path to scene.json")
    parser.add_argument("tiles", help="path to tiles.bin")
    parser.add_argument("sprites", help="path to sprites.bin")
    parser.add_argument("output", help="path to output PNG")
    args = parser.parse_args()
    RenderingPipeline(
        args.palette, args.scene, args.tiles, args.sprites, args.output
    ).render()


if __name__ == "__main__":
    main()
