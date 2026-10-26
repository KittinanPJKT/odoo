{
    'name': 'Tech Appraisal (Demo)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Simple employee appraisal for tech teams',
    'author': 'Demo',
    'depends': ['hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/appraisal_views.xml',
        'views/review_views.xml',
        'views/menus.xml',
        'data/sample_data.xml',
        'data/sample_reviews.xml',
    ],
    'application': False,
    'license': 'LGPL-3',
}
