from hatchet_sdk import Hatchet, EmptyModel, Context

hatchet = Hatchet()


@hatchet.task(on_events=["slack:/incident-bot-test"])
async def simple(_i: EmptyModel, _c: Context) -> None:
    print("Hello, world!")
    return None


def main() -> None:
    worker = hatchet.worker(name="incident-bot", workflows=[simple])
    worker.start()


if __name__ == "__main__":
    main()
