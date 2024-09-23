import requests
import json
import qrcode
import datetime
import time
import os
import pickle
from aiogram.types import InputFile
from aiogram.types import BufferedInputFile
from aiogram.types import FSInputFile


def save_cookies(session, filename):
    with open(filename, 'wb') as file:
        pickle.dump(session.cookies, file)

# Функция для загрузки cookies из файла


def load_cookies(session: requests.Session, filename):
    try:
        with open(filename, 'rb') as file:
            session.cookies.update(pickle.load(file))
    except:
        pass


class Customer():
    '''Базовая информация об клиентах'''

    def __init__(self, id=None,
                 accounts=None,
                 type=None,
                 date=None,
                 tokens=None,
                 firstName='',
                 lastName='',
                 **kwargs):
        self.id = id  # id
        if (accounts != None):
            # баланс
            self.available = accounts[0]['accountBalance']['available']
        self.name = firstName + lastName  # имя, фамилия
        self.type = type  # тип аккаунта
        self.tokens: list = tokens  # индетификационые ключи
        self.date = date  # дата регистрации


class Api():
    '''
    Класс работы с API quickresto
    '''

    headers = {
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
    }

    def __init__(self, login, password) -> None:
        self.login = login
        self.password = password
        self.URL = f'https://{login}.quickresto.ru/platform/online/'
        # self.URL = f'https://{login}.quickresto.ru/api/'

    def _datetime_format(self, date) -> str:
        '''Преобразование даты и времени из QickResto'''
        timedelta = datetime.timedelta(hours=3)
        return (datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ') + timedelta).strftime('%d.%m %H:%M')

    def _json_format(self, data) -> str:
        '''Преобразование словаря в читаемый API QR формат'''
        return str(data).replace('\'', '"').replace(' ', '').encode('utf-8')

    def _get(self, module: str, params=None, json_format=True):
        response = requests.get(
            url=self.URL+module,
            auth=(self.login, self.password),
            headers=self.headers,
            params=params
        )
        try:
            if json_format:
                if response.get('errorCode'):
                    return False
                return response.json()
            else:
                return response
        except:
            return response.text

    def _post(self, module: str, data=None, params=None, json_format=True) -> requests:
        '''Post запрос в API QuickResto и возврат в json формате'''
        response = requests.post(
            url=self.URL+module,
            auth=(self.login, self.password),
            headers=self.headers,
            data=json.dumps(data, ensure_ascii=False).encode('utf8'),
            params=params
        )
        try:
            if json_format:
                return response.json()
            else:
                return response
        except:
            return response.text

    def _save_json(self, response) -> None:
        '''Сохранение данных из API в json формате'''
        with open('data.json', 'w') as base:
            json.dump(response, base)

    def _format_history(self, history) -> list:
        '''Шаблон текста истории начисления\списания баллов'''
        text = list()
        for data in history:
            if data['type'] == 'DEBIT_CONFIRMATION':
                data['type'] = 'Списание'
            elif data['type'] == 'CREDIT':
                data['type'] = 'Начисление'
            else:
                continue
            text.append('{}: {} ({})\n'.format(
                data['type'], data['amount'], self._datetime_format(data['regTime'])))
        return text


class Office:
    def __init__(self, login, password) -> None:
        self.error = 0
        self.URL = 'https://kosplace.quickresto.ru/platform/'
        self.session = requests.Session()
        load_cookies(self.session, 'cookies.pkl')
        self.login = login
        self.password = password

    def log_in(self):
        resp = self.session.post(
            self.URL + 'j_spring_security_check',
            data=f'j_username={self.login}&j_password={self.password}&j_rememberme=true',
            headers={
                'Connection': 'keep-alive',
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
        )
        if resp.status_code == 401:
            print('Логин или пароль')
        save_cookies(self.session, 'cookies.pkl')
        # self.save_cookie(response.cookies)

    def create_token(self, client_id, phone_number):

        response = self.session.post(
            self.URL + 'data/crm.customer.tokens/create',
            params={
                'ownerContextId': client_id,
                'ownerContextClassName': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
                'businessDayOffsetInMs': 0,
                'timeZone': -180
            },
            data=json.dumps({
                "className": "ru.edgex.quickresto.modules.crm.customer.tokens.CrmToken",
                "type": "card",
                "entry": "barCode",
                "key": str(phone_number)})
        )

        if response.status_code == 401 and self.error == 0:
            self.error += 1
            self.log_in()
            time.sleep(1)
            self.create_token(client_id, phone_number)

        self.error = 0
        return response
    
    def _get_credit_account(self, client_id: int):
        url = "data/crm.accounting.account/select"
        params = {
            "start": 0,
            "count": 150,
            "mode": "bonuses",
            "ownerContextId": client_id,
            "ownerContextClassName": "ru.edgex.quickresto.modules.crm.customer.CrmCustomer",
            "businessDayOffsetInMs": 0,
            "timeZone": -180
        }
        response = self.session.post(
            url=self.URL + url,
            params=params
        )
        if response.status_code == 401 and self.error == 0:
            self.error += 1
            self.log_in()
            time.sleep(0.5)
            response = self._get_credit_account(client_id)
        self.error = 0
        if response.status_code == 200:
            data = response.json()
            for obj in data.get('ds'):
                try:
                    if obj['object']['accountType']['accountGuid'] == 'bonus_account_type-1':
                        return obj["object"]["id"]
                except Exception as e:
                    return None

        return None


    def add_credit(self, client_id: int, amount: int):
        bonus_id = self._get_credit_account(client_id)
        if not bonus_id:
            return None
        url = "data/crm.accounting.account/action"
        params = {
            "businessDayOffsetInMs": "0",
            "mode": "bonuses",
            "timeZone": "-180"
        }
        data = json.dumps({
            "actionName": "accountCredit",
            "data": {
                "className":
                "accountCreditModal",
                "ownerContextIds": [bonus_id],
                "amount": amount,
                "timeZone": -180},
            "ids": [bonus_id],
            "owner": {
                "ownerContextId": client_id,
                "ownerContextClassName":
                "ru.edgex.quickresto.modules.crm.customer.CrmCustomer"
            }}
        )
        response = self.session.post(
            url=self.URL + url,
            params=params,
            data=data
        )
        if response.status_code == 200:
            return response.json()
        return response.text



class CRM(Api):

    def find_client(self, search: str):
        response = self._post(
            module='bonuses/filterCustomers', data={'search': search})

        if response.get('errorCode'):
            return False
        if response['customers'] == []:
            return False
        return response['customers'][0]

    def get_client(self, client_id):
        response = self._get(
            module='api/read',
            params={
                'moduleName': 'crm.customer',
                'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
                'objectId': client_id}
        )

        return response

    def edit(self, client_id):

        client = self._get(
            module='api/read',
            params={
                'moduleName': 'crm.customer',
                'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
                'objectId': client_id}
        )

        # print(client)
        data = json.loads(client)
        data['tokens'] = [
            {"type": "phone", "entry": "barCode", "key": "9213215511", "id": 1207}
        ]
        data['firstName'] = 'Тестовый измененный пользователь'

        new_data = self._post(
            module='api/update',
            params={
                'moduleName': 'crm.customer',
                'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer'
            },
            data=data
        )
        print(new_data)

    def get_info(self, phone_number):
        response = self._post(
            'bonuses/getCustomer',
            data={"customerToken": {"type": "card",
                                    "entry": "barCode", "key": str(phone_number)}}
        )
        return response
    
    def get_bonus_account(self, phone_number):
        response = self._post(
            'bonuses/balance',
            data={
                "customerToken": {"type": "card", "entry": "barCode", "key": str(phone_number)},
                "accountType": {'accountGuid': 'bonus_account_type-1'}}
        )
        return response

    def get_balance(self, phone_number):
        response = self._post(
            'bonuses/balance',
            data={
                "customerToken": {"type": "card", "entry": "barCode", "key": str(phone_number)},
                "accountType": {'accountGuid': 'bonus_account_type-1'}}
        )
        return response['accountBalance']['available']

    def get_history(self, phone_number):
        response = self._post(
            'bonuses/operationHistory',
            data={
                "customerToken": {"type": "card", "entry": "barCode", "key": str(phone_number)},
                "accountType": {'accountGuid': 'bonus_account_type-1'}}
        )
        return self._format_history(response.get('transactions'))

    def create_token(self, phone_number):

        response = self._post(
            'api/create',
            params={
                "ownerContextId": 15566,
                'ownerContextClassName': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
                'moduleName': 'crm.customer.tokens',
                'className': 'ru.edgex.quickresto.modules.crm.customer.tokens.CrmToken'},
            data={'type': 'card',
                  'entry': 'barCode',
                  'key': str(phone_number)},
        )
        return response

    def create(self, name, phone_number, telegram_id):

        user = {
            'firstName': name,
            'contactMethods': [{
                'type': 'phoneNumber',
                'value': str(phone_number)
            }],
        }

        response = self._post(
            'api/create',
            params={'moduleName': 'crm.customer',
                    'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer'},
            data=user
        )
        return response

    def qr_code(self, phone_number):
        '''Формирование QR кода'''
        try:
            open(f'files/qr/qr_{phone_number}.png', 'rb')
            text_file = FSInputFile(f'files/qr/qr_{phone_number}.png', 'qr')
            return text_file
        except:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(phone_number)
            img = qr.make_image(fill_color="black", back_color="white")
            try:
                img.save(f'files/qr/qr_{phone_number}.png')
                text_file = FSInputFile(
                    f'files/qr/qr_{phone_number}.png', 'qr')
                return text_file
            except:
                os.mkdir('files')
                os.mkdir('files/qr')
                img.save(f'files/qr/qr_{phone_number}.png')
                text_file = FSInputFile(
                    f'files/qr/qr_{phone_number}.png', 'qr')
                return text_file


class CustomerOperation(Api):
    '''Операции с клиентсикими обьектами'''

    def createCustomer(self, firstName='', phone_number=None, telegram_id=None):
        ''' Создание гостя в системе QuickResto'''

        url = self.url + 'bonuses/createCustomer'
        tokens = list()
        if phone_number:
            tokens.append({
                'type': 'phone',
                'entry': 'manual',
                'key': phone_number
            })
        if telegram_id:
            tokens.append({
                'type': 'card',
                'entry': 'barCode',
                'key': telegram_id
            })
        data = {
            'firstName': firstName,
            # 'lastName': lastName,
            # 'dateOfBirth': datetime, #'1990-03-07T19:00:00.000Z'
            'tokens': tokens
        }
        return self._post(url, self._json_format(data))

    def filterCustomer(self, phone_number):
        '''Фильтрация гостей по номеру'''

        url = self.url + 'bonuses/filterCustomers'
        data = {'search': phone_number}
        return self._post(url, self._json_format(data))

    def getCustomer(self, telegram_id=None, phone_number=None):
        '''Получить обьект Customer из API'''

        url = self.url + 'bonuses/customerInfo'
        if telegram_id:
            data = {
                "customerToken": {
                    "type": "card",
                    "entry": "barCode",
                    "key": telegram_id
                }}
        if phone_number:
            try:
                data = {
                    "customerToken": {
                        'type': 'phone',
                        'entry': 'manual',
                        'key': self.filterCustomer(phone_number)['customers'][0]['contactMethods'][0]['value'],
                    }
                }
            except:
                data = {
                    "customerToken": {
                        'type': 'phone',
                        'entry': 'manual',
                        'key': phone_number
                    }}
        return self._post(url, self._json_format(data))

    def addToken(self, id, token):
        url_reg = f'https://{self.login}.quickresto.ru/platform/j_spring_security_check'
        data = f'j_username={self.login}&j_password={self.password}&j_rememberme=true'
        headers = {
            'Connection': 'keep-alive',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        reg = requests.post(url_reg, data=data, headers=headers)
        cookies = reg.cookies
        time.sleep(1)
        url = 'https://kosplace.quickresto.ru/platform/data/crm.customer.tokens/create?ownerContextId=%s&ownerContextClassName=ru.edgex.quickresto.modules.crm.customer.CrmCustomer&businessDayOffsetInMs=0&timeZone=-180' % id
        data_2 = '{"className":"ru.edgex.quickresto.modules.crm.customer.tokens.CrmToken","type":"card","entry":"barCode","key":"%s"}' % token
        if requests.post(url, data=data_2, cookies=cookies).status_code == 200:
            return True
        else:
            return False


class Crm_info(CustomerOperation):
    '''
    Выгрузка данных из CRM об клиента (история транцакций,
    баланс бонусов, формирование QR кода для авторизации)
    '''

    def client_balance(self, phone_number) -> str:
        '''Кол-во бонусов клиента (поиск по telegram_id)'''

        url = self.url + 'bonuses/balance'
        try:
            data = {
                "customerToken": {
                    'type': 'phone',
                    'entry': 'manual',
                    'key': int(self.filterCustomer(phone_number)['customers'][0]['contactMethods'][0]['value']),
                },
                "accountType": {
                    "accountGuid": "bonus_account_type-1"
                }
            }
        except:
            data = {
                "customerToken": {
                    'type': 'phone',
                    'entry': 'manual',
                    'key': phone_number
                },
                "accountType": {
                    "accountGuid": "bonus_account_type-1"}
            }
        try:
            return self._post(url, self._json_format(data))['accountBalance']['available']
        except:
            return 0

    def client_history(self, phone_number):
        '''История транзакций в бонусной системе клиента'''

        url = self.url + 'bonuses/operationHistory'
        try:
            data = {
                "customerToken": {
                    'type': 'phone',
                    'entry': 'manual',
                    'key': int(self.filterCustomer(phone_number)['customers'][0]['contactMethods'][0]['value']),
                },
                "accountType": {
                    "accountGuid": "bonus_account_type-1"
                }
            }
        except:
            data = {
                "customerToken": {
                    'type': 'phone',
                    'entry': 'manual',
                    'key': phone_number
                },
                "accountType": {
                    "accountGuid": "bonus_account_type-1"}
            }
        try:
            return self._format_history(self._post(url, self._json_format(data))['transactions'])
        except:
            return 'Транзакции отсутствуют'

    def qr_code(self, phone_number):
        '''Формирование QR кода'''
        try:
            return open('files/qr/qr_%d.png' % phone_number, 'rb')
        except:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(phone_number)
            img = qr.make_image(fill_color="black", back_color="white")
            try:
                img.save(f'files/qr/qr_{phone_number}.png')
                return open(f'files/qr/qr_{phone_number}.png', 'rb')
            except:
                os.mkdir('files')
                os.mkdir('files/qr')
                img.save(f'files/qr/qr_{phone_number}.png')
                return open(f'files/qr/qr_{phone_number}.png', 'rb')


if __name__ == '__main__':
    api = CRM(os.getenv('login_api'), os.getenv('password_api'))
    lk = Office(os.getenv('login_lk'), os.getenv('password_lk'))
    # data = lk.
    data = api.get_balance(9969290700)
    print(data)
    # data = api.create('Тестовый пользоваьель 10', '9213215510', 4930400310)
    # data = api.edit(15566)
    # data = api.create_token('1239348398499')
    # data = api.get_balance()
    # print(data)
