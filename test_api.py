import requests

BASE = 'http://127.0.0.1:8000/api'
S = requests.Session()
headers = {'Origin': 'http://127.0.0.1:5174'}

print('GET csrf...')
r = S.get(BASE + '/auth/csrf/', headers=headers)
print('status', r.status_code)
print('headers:', r.headers.get('access-control-allow-origin'), r.headers.get('access-control-allow-credentials'))
print('cookies:', S.cookies.get_dict())

print('\nPOST login...')
p = {'username': 'admin', 'password': 'Admin@12345'}
r = S.post(BASE + '/auth/login/', json=p, headers=headers)
print('status', r.status_code)
print('resp', r.text)
print('cookies after login:', S.cookies.get_dict())

print('\nPOST transaction...')
# pick existing category/account ids
body = {'transaction_type': 'income', 'title': 'cli test', 'amount': '10', 'category': 1, 'account': 1, 'date': '2026-07-06', 'payment_method': 'cash'}
# set X-CSRFToken from cookie
csrf = S.cookies.get('csrftoken')
if csrf:
    headers['X-CSRFToken'] = csrf
r = S.post(BASE + '/transactions/', json=body, headers=headers)
print('status', r.status_code)
print('resp', r.text)

