import aiohttp
import json
import qrcode
import datetime
import time
import os
import pickle
import logging
from aiogram.types import FSInputFile
from typing import Optional, Any, Union
from aiohttp_socks import ProxyConnector

try:
    from settings import settings
except ImportError:
    from app.settings import settings

logger = logging.getLogger(__name__)

async def save_cookies(session: aiohttp.ClientSession, filename: str):
    cookies = {}
    for cookie in session.cookie_jar:
        cookies[cookie.key] = cookie.value
    with open(filename, 'wb') as file:
        pickle.dump(cookies, file)

async def load_cookies(session: aiohttp.ClientSession, filename: str):
    try:
        if os.path.exists(filename):
            with open(filename, 'rb') as file:
                cookies = pickle.load(file)
                session.cookie_jar.update_cookies(cookies)
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")

class Api:
    '''
    Класс работы с API quickresto (асинхронный)
    '''
    headers = {
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
    }

    def __init__(self, login, password, session: aiohttp.ClientSession) -> None:
        self.login = login
        self.password = password
        self.session = session
        self.URL = f'https://{login}.quickresto.ru/platform/online/'
        self.proxy = settings.PROXY_URL

    def _datetime_format(self, date) -> str:
        '''Преобразование даты и времени из QickResto'''
        try:
            timedelta = datetime.timedelta(hours=3)
            return (datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ') + timedelta).strftime('%d.%m %H:%M')
        except Exception:
            return date

    def _get_proxy_kwargs(self):
        if self.proxy and (not self.session.connector or not isinstance(self.session.connector, ProxyConnector)):
            return {'proxy': self.proxy}
        return {}

    async def _get(self, module: str, params=None, json_format=True):
        proxy_kwargs = self._get_proxy_kwargs()
        try:
            async with self.session.get(
                url=self.URL + module,
                auth=aiohttp.BasicAuth(self.login, self.password),
                headers=self.headers,
                params=params,
                **proxy_kwargs
            ) as response:
                if json_format:
                    data = await response.json()
                    if isinstance(data, dict) and data.get('errorCode'):
                        return False
                    return data
                else:
                    return await response.text()
        except Exception as e:
            logger.error(f"GET error: {e}")
            return False

    async def _post(self, module: str, data=None, params=None, json_format=True):
        '''Post запрос в API QuickResto и возврат в json формате'''
        proxy_kwargs = self._get_proxy_kwargs()
        try:
            async with self.session.post(
                url=self.URL + module,
                auth=aiohttp.BasicAuth(self.login, self.password),
                headers=self.headers,
                json=data,
                params=params,
                **proxy_kwargs
            ) as response:
                if json_format:
                    return await response.json()
                else:
                    return await response.text()
        except Exception as e:
            logger.error(f"POST error: {e}")
            return False

class Office:
    def __init__(self, login, password, session: aiohttp.ClientSession) -> None:
        self.error_count = 0
        self.URL = f'https://{login}.quickresto.ru/platform/'
        self.session = session
        self.login = login
        self.password = password
        self.proxy = settings.PROXY_URL
        self.cookie_file = 'cookies.pkl'

    def _get_proxy_kwargs(self):
        if self.proxy and (not self.session.connector or not isinstance(self.session.connector, ProxyConnector)):
            return {'proxy': self.proxy}
        return {}

    async def log_in(self):
        proxy_kwargs = self._get_proxy_kwargs()
        try:
            data = {
                'j_username': self.login,
                'j_password': self.password,
                'j_rememberme': 'true'
            }
            async with self.session.post(
                self.URL + 'j_spring_security_check',
                data=data,
                headers={
                    'Connection': 'keep-alive',
                    'Accept': 'application/json, text/plain, */*',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                **proxy_kwargs
            ) as resp:
                if resp.status == 401:
                    logger.error('Login failed: Invalid login or password')
                    return False
                await save_cookies(self.session, self.cookie_file)
                return True
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    async def create_token(self, client_id, phone_number):
        params = {
            'ownerContextId': client_id,
            'ownerContextClassName': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
            'businessDayOffsetInMs': 0,
            'timeZone': -180
        }
        data = {
            "className": "ru.edgex.quickresto.modules.crm.customer.tokens.CrmToken",
            "type": "card",
            "entry": "barCode",
            "key": str(phone_number)
        }

        proxy_kwargs = self._get_proxy_kwargs()
        async with self.session.post(
            self.URL + 'data/crm.customer.tokens/create',
            params=params,
            json=data,
            **proxy_kwargs
        ) as response:
            if response.status == 401 and self.error_count == 0:
                self.error_count += 1
                if await self.log_in():
                    return await self.create_token(client_id, phone_number)

            self.error_count = 0
            return response

    async def _get_credit_account(self, client_id: int):
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
        proxy_kwargs = self._get_proxy_kwargs()
        async with self.session.post(
            url=self.URL + url,
            params=params,
            **proxy_kwargs
        ) as response:
            if response.status == 401 and self.error_count == 0:
                self.error_count += 1
                if await self.log_in():
                    return await self._get_credit_account(client_id)

            self.error_count = 0
            if response.status == 200:
                data = await response.json()
                for obj in data.get('ds', []):
                    try:
                        if obj['object']['accountType']['accountGuid'] == 'bonus_account_type-1':
                            return obj["object"]["id"]
                    except Exception:
                        continue
        return None

    async def add_credit(self, client_id: int, amount: int):
        bonus_id = await self._get_credit_account(client_id)
        if not bonus_id:
            return None
        url = "data/crm.accounting.account/action"
        params = {
            "businessDayOffsetInMs": "0",
            "mode": "bonuses",
            "timeZone": "-180"
        }
        data = {
            "actionName": "accountCredit",
            "data": {
                "className": "accountCreditModal",
                "ownerContextIds": [bonus_id],
                "amount": amount,
                "timeZone": -180
            },
            "ids": [bonus_id],
            "owner": {
                "ownerContextId": client_id,
                "ownerContextClassName": "ru.edgex.quickresto.modules.crm.customer.CrmCustomer"
            }
        }
        proxy_kwargs = self._get_proxy_kwargs()
        async with self.session.post(
            url=self.URL + url,
            params=params,
            json=data,
            **proxy_kwargs
        ) as response:
            if response.status == 200:
                return await response.json()
            return await response.text()

class CRM(Api):
    async def find_client(self, search: str):
        response = await self._post(
            module='bonuses/filterCustomers', data={'search': search})
        if not response or response.get('errorCode'):
            return False
        if not response.get('customers'):
            return False
        return response['customers'][0]

    async def get_client(self, client_id):
        return await self._get(
            module='api/read',
            params={
                'moduleName': 'crm.customer',
                'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer',
                'objectId': client_id}
        )

    async def get_info(self, phone_number):
        return await self._post(
            'bonuses/getCustomer',
            data={"customerToken": {"type": "card",
                                    "entry": "barCode", "key": str(phone_number)}}
        )
    
    async def get_balance(self, phone_number):
        response = await self._post(
            'bonuses/balance',
            data={
                "customerToken": {"type": "card", "entry": "barCode", "key": str(phone_number)},
                "accountType": {'accountGuid': 'bonus_account_type-1'}}
        )
        if response and 'accountBalance' in response:
            return response['accountBalance']['available']
        return 0

    async def get_history(self, phone_number):
        response = await self._post(
            'bonuses/operationHistory',
            data={
                "customerToken": {"type": "card", "entry": "barCode", "key": str(phone_number)},
                "accountType": {'accountGuid': 'bonus_account_type-1'}}
        )
        if response and 'transactions' in response:
            return self._format_history(response.get('transactions'))
        return []

    def _format_history(self, history) -> list:
        text = list()
        for data in history:
            if data['type'] == 'DEBIT_CONFIRMATION':
                t = 'Списание'
            elif data['type'] == 'CREDIT':
                t = 'Начисление'
            else:
                continue
            text.append('{}: {} ({})\n'.format(
                t, data['amount'], self._datetime_format(data['regTime'])))
        return text

    async def create(self, name, phone_number, telegram_id):
        user = {
            'firstName': name,
            'contactMethods': [{
                'type': 'phoneNumber',
                'value': str(phone_number)
            }],
        }
        return await self._post(
            'api/create',
            params={'moduleName': 'crm.customer',
                    'className': 'ru.edgex.quickresto.modules.crm.customer.CrmCustomer'},
            data=user
        )

    def qr_code(self, phone_number):
        file_path = f'files/qr/qr_{phone_number}.png'
        if os.path.exists(file_path):
            return FSInputFile(file_path, 'qr')

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(phone_number)
        img = qr.make_image(fill_color="black", back_color="white")

        os.makedirs('files/qr', exist_ok=True)
        img.save(file_path)
        return FSInputFile(file_path, 'qr')

class CustomerOperation(Api):
    async def createCustomer(self, firstName='', phone_number=None, telegram_id=None):
        url = 'bonuses/createCustomer'
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
            'tokens': tokens
        }
        return await self._post(url, data)

    async def filterCustomer(self, phone_number):
        url = 'bonuses/filterCustomers'
        data = {'search': phone_number}
        return await self._post(url, data)

    async def getCustomer(self, telegram_id=None, phone_number=None):
        url = 'bonuses/customerInfo'
        data = {}
        if telegram_id:
            data = {
                "customerToken": {
                    "type": "card",
                    "entry": "barCode",
                    "key": telegram_id
                }}
        elif phone_number:
            filtered = await self.filterCustomer(phone_number)
            try:
                key = filtered['customers'][0]['contactMethods'][0]['value']
            except (KeyError, IndexError, TypeError):
                key = phone_number
            data = {
                "customerToken": {
                    'type': 'phone',
                    'entry': 'manual',
                    'key': key,
                }
            }
        return await self._post(url, data)
