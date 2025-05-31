from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    ref = State()
    number = State()

class AskForm(StatesGroup):
    ask = State()

class MessageForm(StatesGroup):
    message = State()
    confirm = State()
    cancel = State()

class UpdateMenuStates(StatesGroup):
    choosing = State() 
    waiting_photo = State()