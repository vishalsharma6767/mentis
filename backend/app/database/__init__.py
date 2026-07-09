"""Database setup: Appwrite client, collection management, migrations."""

from appwrite.client import Client
from appwrite.services.databases import Databases

from app.core.config import settings

client = Client()
client.set_endpoint(settings.appwrite_endpoint)
client.set_project(settings.appwrite_project_id)
client.set_key(settings.appwrite_api_key)

databases = Databases(client)

DATABASE_ID = 'mentis_main'
COLLECTIONS = {
    'sessions': [
        {'key': 'userId', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'problemTitle', 'type': 'string', 'size': 512, 'required': False},
        {'key': 'problemImage', 'type': 'string', 'size': 255, 'required': False},
        {'key': 'extractedText', 'type': 'string', 'size': 16384, 'required': False},
        {'key': 'problemType', 'type': 'string', 'size': 64, 'required': False},
        {'key': 'status', 'type': 'string', 'size': 64, 'required': True},
        {'key': 'steps', 'type': 'string', 'size': 65536, 'required': False},
        {'key': 'createdAt', 'type': 'datetime', 'required': False},
    ],
    'progress': [
        {'key': 'userId', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'topic', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'mastered', 'type': 'boolean', 'required': True},
        {'key': 'mistakes', 'type': 'integer', 'required': False},
        {'key': 'sessionsCount', 'type': 'integer', 'required': False},
        {'key': 'lastPracticed', 'type': 'datetime', 'required': False},
    ],
    'problems': [
        {'key': 'userId', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'imageId', 'type': 'string', 'size': 255, 'required': False},
        {'key': 'text', 'type': 'string', 'size': 16384, 'required': True},
        {'key': 'type', 'type': 'string', 'size': 64, 'required': True},
        {'key': 'solution', 'type': 'string', 'size': 65536, 'required': False},
    ],
    'discussions': [
        {'key': 'userId', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'title', 'type': 'string', 'size': 512, 'required': True},
        {'key': 'body', 'type': 'string', 'size': 8192, 'required': False},
        {'key': 'tag', 'type': 'string', 'size': 64, 'required': False},
        {'key': 'replies', 'type': 'integer', 'required': False},
        {'key': 'likes', 'type': 'integer', 'required': False},
        {'key': 'authorName', 'type': 'string', 'size': 255, 'required': False},
        {'key': 'createdAt', 'type': 'datetime', 'required': False},
    ],
    'study_groups': [
        {'key': 'name', 'type': 'string', 'size': 255, 'required': True},
        {'key': 'subject', 'type': 'string', 'size': 128, 'required': True},
        {'key': 'members', 'type': 'integer', 'required': False},
        {'key': 'active', 'type': 'integer', 'required': False},
        {'key': 'nextSession', 'type': 'string', 'size': 255, 'required': False},
        {'key': 'createdAt', 'type': 'datetime', 'required': False},
    ],
}

ATTR_CREATORS = {
    'string': databases.create_string_attribute,
    'integer': databases.create_integer_attribute,
    'boolean': databases.create_boolean_attribute,
    'datetime': databases.create_datetime_attribute,
}


def get_or_create_database():
    try:
        db = databases.get(DATABASE_ID)
        print(f'Database exists: {db.name}')
        return DATABASE_ID
    except Exception:
        db = databases.create(database_id=DATABASE_ID, name='Mentis Main')
        print(f'Created database: {db.name}')
        return db.id


def get_or_create_collection(database_id: str, collection_name: str):
    try:
        col = databases.get_collection(database_id, collection_name)
        print(f'Collection exists: {col.name}')
        return col.id
    except Exception:
        col = databases.create_collection(
            database_id=database_id,
            collection_id=collection_name,
            name=collection_name,
            permissions=['read("any")', 'write("any")'],
        )
        print(f'Created collection: {collection_name}')
        return col.id


def create_attributes(database_id: str, collection_id: str, attributes: list):
    existing = {a.key: a for a in databases.list_attributes(database_id, collection_id).attributes}
    for attr in attributes:
        key = attr['key']
        if key in existing:
            print(f'  Attribute exists: {key}')
            continue
        creator = ATTR_CREATORS.get(attr['type'])
        if not creator:
            print(f'  Unknown type: {attr["type"]} for {key}')
            continue
        kwargs = {'database_id': database_id, 'collection_id': collection_id, 'key': key, 'required': attr['required']}
        if attr['type'] == 'string':
            kwargs['size'] = attr.get('size', 255)
        if attr.get('min') is not None:
            kwargs['min'] = attr['min']
        if attr.get('max') is not None:
            kwargs['max'] = attr['max']
        creator(**kwargs)
        print(f'  Created attribute: {key} ({attr["type"]})')


def setup_database():
    database_id = get_or_create_database()
    for collection_name, attributes in COLLECTIONS.items():
        collection_id = get_or_create_collection(database_id, collection_name)
        create_attributes(database_id, collection_id, attributes)
    print('\nDatabase setup complete!')


if __name__ == '__main__':
    setup_database()
