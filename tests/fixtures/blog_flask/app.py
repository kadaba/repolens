from flask import Flask
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime

app = Flask(__name__)
Base = declarative_base()


class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    body = Column(Text)
    author_id = Column(Integer)
    published_at = Column(DateTime)


class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer)
    author = Column(String(100))
    body = Column(Text)


class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True)
    name = Column(String(50))


@app.route('/posts', methods=['GET'])
def list_posts():
    return []


@app.route('/posts/<int:post_id>', methods=['GET'])
def get_post(post_id):
    return {}


@app.route('/posts/<int:post_id>/comments', methods=['POST'])
def add_comment(post_id):
    return {}


@app.route('/feed.rss', methods=['GET'])
def rss_feed():
    return ""


@app.route('/tags/<tag>', methods=['GET'])
def by_tag(tag):
    return []
