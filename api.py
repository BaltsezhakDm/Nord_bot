import requests
import json
import qrcode
import datetime
import time
import os

import config


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
    # url для входа в API QuickResto
    URL = 'https://{login}.quickresto.ru/platform/online/'.format(
        login=config.login)

    def _datetime_format(self, date) -> str:
        '''Преобразование даты и времени из QickResto'''
        timedelta = datetime.timedelta(hours=3)
        return (datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ') + timedelta).strftime('%d.%m %H:%M')

    def _json_format(self, data) -> str:
        '''Преобразование словаря в читаемый API QR формат'''
        return str(data).replace('\'', '"').replace(' ', '').encode('utf-8')

    def _post(self, url, data=None, params=None, json=True) -> requests:
        '''Post запрос в API QuickResto и возврат в json формате'''
        response = requests.post(
            url=url,
            auth=(config.login, config.password),
            headers=self.headers,
            data=data,
            params=params
        )
        if json:
            return response.json()
        else:
            return response

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


class CustomerOperation(Api):
    '''Операции с клиентсикими обьектами'''

    def createCustomer(self, firstName='', phone_number=None, telegram_id=None):
        ''' Создание гостя в системе QuickResto'''

        url = self.URL + 'bonuses/createCustomer'
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

        url = self.URL + 'bonuses/filterCustomers'
        data = {'search': phone_number}
        return self._post(url, self._json_format(data))

    def getCustomer(self, telegram_id=None, phone_number=None):
        '''Получить обьект Customer из API'''

        url = self.URL + 'bonuses/customerInfo'
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
        url_reg = 'https://kosplace.quickresto.ru/platform/j_spring_security_check'
        data = 'j_username={}&j_password={}&j_rememberme=true'.format(config.adminLogin, config.adminPassword)
        headers = {
            'Connection': 'keep-alive',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
            }
        reg = requests.post(url_reg, data=data, headers=headers)
        cookies = reg.cookies
        time.sleep(1)
        url = 'https://kosplace.quickresto.ru/platform/data/crm.customer.tokens/create?ownerContextId=%s&ownerContextClassName=ru.edgex.quickresto.modules.crm.customer.CrmCustomer&businessDayOffsetInMs=0&timeZone=-180' %id
        data_2='{"className":"ru.edgex.quickresto.modules.crm.customer.tokens.CrmToken","type":"card","entry":"barCode","key":"%s"}' %token
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

        url = self.URL + 'bonuses/balance'
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

        url = self.URL + 'bonuses/operationHistory'
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
                img.save('files/qr/qr_%d.png' % phone_number)
                return open('files/qr/qr_%d.png' % phone_number, 'rb')
            except:
                os.mkdir('files')
                os.mkdir('files/qr')
                img.save('files/qr/qr_%d.png' % phone_number)
                return open('files/qr/qr_%d.png' % phone_number, 'rb')


if __name__ == '__main__':
    pass