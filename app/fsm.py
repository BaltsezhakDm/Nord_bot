from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    ref = State()
    number = State()

class AskForm(StatesGroup):
    ask = State()
