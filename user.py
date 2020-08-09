#!/usr/bin/env python3
from . import db
import flask_login

from werkzeug.security import generate_password_hash, check_password_hash


class User(flask_login.mixins):
    def __init__(self, email=None):
        self.email = email

    def _load(self, attrib):
        for k, v in attrib.items():
            setattr(self, k, v)

    @staticmethod
    def get(user_id):
        res = db.get('users', user_id)
        if res:
            return User()._load(res)

    def set_password(what):
        hash = generate_password_hash(what)
        # TODO: Incomplete.
        # TODO: Generate the hash at the client?
