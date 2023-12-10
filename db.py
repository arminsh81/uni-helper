from peewee import SqliteDatabase, Model, AutoField, TextField, BooleanField, BigIntegerField, DateTimeField, \
    IntegerField
from cachetools import cached, TTLCache
import datetime
import pytz

db = SqliteDatabase('database.sqlite3')


class Tasks(Model):
    task_id = AutoField()
    task_name = TextField()
    desc = TextField()
    admin_id = BigIntegerField()
    deadline = DateTimeField()
    size_limit = IntegerField()
    file_suffix = TextField()
    active = BooleanField(default=True)
    finished = BooleanField(default=False)

    class Meta:
        database = db

    def deactivate(self):
        self.active = False
        self.save()

    def activate(self):
        self.active = True
        self.save()

    def finish(self):
        self.finished = True
        self.active = False
        self.save()

    def change_deadline(self, new_deadline):
        self.deadline = new_deadline
        self.save()


class Admins(Model):
    user_id = BigIntegerField(unique=True)

    class Meta:
        database = db


db.connect()
db.create_tables([Tasks, Admins], safe=True)

get_tasks_cache = TTLCache(maxsize=100, ttl=60)


@cached(get_tasks_cache)
def get_tasks() -> list[Tasks]:
    return Tasks.select().where(
        Tasks.active & ~Tasks.finished &
        (Tasks.deadline > datetime.datetime.now(tz=pytz.timezone('Asia/Tehran'))))


get_task_cache = TTLCache(maxsize=100, ttl=60)


@cached(get_task_cache)
def get_task(task_id) -> Tasks:
    res = Tasks.get(Tasks.task_id == task_id)
    return res


def get_task_admin(task_id) -> Tasks:  # this version is not cached
    res = Tasks.get(Tasks.task_id == task_id)
    return res


def add_admin(user_id):
    Admins.create(user_id=user_id)
    return True


def delete_admin(user_id):
    query = Admins.delete().where(Admins.user_id == user_id)
    query.execute()
    return True


admin_list_cache = TTLCache(maxsize=100, ttl=600)


@cached(admin_list_cache)
def admin_list():
    return [row.user_id for row in Admins.select()]


def is_admin(user_id):
    return user_id in admin_list()


def get_admin_tasks(admin_id, sudo=False):
    return Tasks.select().where(((Tasks.admin_id == admin_id) | sudo == True )& (Tasks.finished == False))

