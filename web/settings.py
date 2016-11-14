config = {
    'db_name': 'temba',
    'db_host': 'localhost',
    'db_user': 'postgres',
    'db_passwd': 'postgres',
    'db_port': '5432',
    'logfile': '/tmp/tmcg-web.log',
    'kannel_log_dir': '/Users/sam/projects/tmcg',
    'python_script': '/var/www/env/dev/bin/python',
    # Network RegEx for Kannel logs
    'network_regex': {
        'mtn': '256(3[19]|7[78])',
        'airtel': '2567[05]',
        'africel': '25679',
        'utl': '25671',
        'others': '256(3[19]|41|7[015789])'  # opssite of
    },
    # 'default_api_uri': 'http://hiwa.tmcg.co.ug/api/v1/contacts.json',
    'default_api_uri': 'http://localhost:8000/api/v1/contacts.json',
    # 'api_token': '3a0a09ef35595037568b2ac9b71871b695f9a3e8',
    'api_token': 'c8cde9dbbdda6f544018e9321d017e909b28ec51',
}
