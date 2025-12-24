from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super_secret_key'

PREDEFINED_USERS = {
    "user": "user1",
    "admin": "admin1"
}

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Глобальные списки для фото и комментариев
photos = []
comments = []


def load_users():
    users = {}
    global photos, comments

    # Сбрасываем списки перед загрузкой
    photos.clear()
    comments.clear()

    if os.path.exists("users.txt"):
        with open("users.txt", "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue

                parts = line.split("::")
                if len(parts) < 2:
                    continue

                username = parts[0]
                password = parts[1]
                user_photos = parts[2].split("|") if len(parts) > 2 else []
                user_comments = parts[3].split("|") if len(parts) > 3 else []

                # Восстанавливаем фото пользователя
                user_photos_list = []
                for p_str in user_photos:
                    if not p_str:
                        continue
                    p_data = p_str.split(",")
                    if len(p_data) >= 5:
                        photo = {
                            "id": p_data[0],
                            "author": username,
                            "filename": p_data[1],
                            "description": p_data[2],
                            "tags": p_data[3].split(";"),
                            "date": p_data[4]
                        }
                        user_photos_list.append(photo)
                        photos.append(photo)

                # Восстанавливаем комментарии пользователя
                user_comments_list = []
                for c_str in user_comments:
                    if not c_str:
                        continue
                    c_data = c_str.split(",")
                    if len(c_data) >= 6:
                        comment = {
                            "id": c_data[0],
                            "photo_id": c_data[1],
                            "parent_id": c_data[2] if c_data[2] != "None" else None,
                            "author": username,
                            "text": c_data[3],
                            "date": c_data[4],
                            "edited": c_data[5] == "True"
                        }
                        user_comments_list.append(comment)
                        comments.append(comment)

                # ИСПРАВЛЕНО: Гарантируем наличие полей для всех пользователей
                users[username] = {
                    "password": password,
                    "photos": user_photos_list if user_photos_list else [],
                    "comments": user_comments_list if user_comments_list else []
                }

    # ИСПРАВЛЕНО: Добавляем предопределенных пользователей с пустыми списками
    for username, password in PREDEFINED_USERS.items():
        if username not in users:
            users[username] = {
                "password": password,
                "photos": [],
                "comments": []
            }

    return users


def save_users(users):
    global photos, comments

    with open("users.txt", "w", encoding="utf-8") as file:
        for username, data in users.items():
            # Форматируем фото для сохранения
            photos_str = []
            for p in data["photos"]:
                tags_str = ";".join(p["tags"])
                p_str = f"{p['id']},{p['filename']},{p['description']},{tags_str},{p['date']}"
                photos_str.append(p_str)
            photos_str = "|".join(photos_str)

            # Форматируем комментарии для сохранения
            comments_str = []
            for c in data["comments"]:
                parent_id = c["parent_id"] or "None"
                edited = "True" if c["edited"] else "False"
                c_str = f"{c['id']},{c['photo_id']},{parent_id},{c['text']},{c['date']},{edited}"
                comments_str.append(c_str)
            comments_str = "|".join(comments_str)

            line = f"{username}::{data['password']}::{photos_str}::{comments_str}\n"
            file.write(line)

    # Обновляем глобальные списки
    photos = [p for u in users.values() for p in u["photos"]]
    comments = [c for u in users.values() for c in u["comments"]]


def save_user(username, password):
    with open("users.txt", "a", encoding="utf-8") as file:
        file.write(f"{username}::{password}::::\n")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            flash("Для этого действия нужно войти в аккаунт.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# Декоратор для страниц просмотра: разрешаем гостям, но редиректим на логин, если режим не выбран
def view_route(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session and 'guest' not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated




@app.route("/continue_as_guest")
def continue_as_guest():
    # Очищаем сессию пользователя, если она была
    session.pop('user', None)
    # Устанавливаем флаг гостя
    session['guest'] = True
    flash("Ты просматриваешь сайт как гость. Чтобы комментировать и публиковать — войди или зарегистрируйся.", "info")
    return redirect(url_for("feed"))

@app.route('/')
def index():
    # Если пользователь авторизован — сразу в ленту
    if 'user' in session:
        return redirect(url_for("feed"))
    # Если гость — тоже в ленту
    elif 'guest' in session:
        return redirect(url_for("feed"))
    # Иначе — на страницу логина
    else:
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        all_users = load_users()
        users_simple = {u: d["password"] for u, d in all_users.items()}
        users_combined = {**PREDEFINED_USERS, **users_simple}

        if username in users_combined and users_combined[username] == password:
            # Очищаем флаг гостя, если он был
            session.pop('guest', None)
            # Устанавливаем сессию пользователя
            session['user'] = username
            flash(f"Добро пожаловать, {username}!", "success")
            # Прямо редиректим в ленту (не через промежуточный шаг)
            return redirect(url_for("feed"))
        else:
            flash("Неверные данные! Зарегистрируйтесь.", "error")
    return render_template("login.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        all_users = load_users()

        if not username or not new_password or not confirm_password:
            flash("Заполните все поля формы!", "error")
            return redirect(url_for("reset_password"))

        if username not in all_users:
            flash("Пользователь с таким логином не найден!", "error")
            return redirect(url_for("reset_password"))

        if new_password != confirm_password:
            flash("Пароли не совпадают!", "error")
            return redirect(url_for("reset_password"))

        all_users[username]["password"] = new_password
        save_users(all_users)

        flash("Пароль успешно изменен! Теперь вы можете войти.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm = request.form.get("password_confirm", "").strip()

        if not username or not password:
            flash("Все поля обязательны.", "error")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Пароли не совпадают.", "error")
            return redirect(url_for("register"))

        users = load_users()
        if username in users:
            flash("Такой пользователь уже существует.", "error")
            return redirect(url_for("login"))

        save_user(username, password)
        flash("Регистрация успешно завершена! Теперь войдите.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop('user', None)
    session.pop('guest', None)
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("login"))


@app.route("/feed")
@view_route
def feed():
    sorted_photos = sorted(photos, key=lambda x: x['date'], reverse=True)
    return render_template("feed.html", photos=sorted_photos)

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        if 'photo' not in request.files:
            flash("Вы не выбрали фото!", "error")
            return redirect(url_for('upload'))

        file = request.files['photo']
        description = request.form.get('description', '').strip()
        tags = request.form.get('tags', '').strip().lower().split(',')
        tags = [t.strip() for t in tags if t.strip()]

        if file.filename == '':
            flash("Вы не выбрали фото!", "error")
            return redirect(url_for('upload'))

        if not tags:
            flash("Добавьте хотя бы один тег!", "error")
            return redirect(url_for('upload'))

        filename = secure_filename(f"{session['user']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Добавляем фото в глобальный список
        photo_id = str(len(photos) + 1)
        new_photo = {
            "id": photo_id,
            "author": session['user'],
            "filename": filename,
            "description": description,
            "tags": tags,
            "date": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        photos.append(new_photo)

        # --- УПРОЩЕННАЯ ЛОГИКА СОХРАНЕНИЯ ---
        users = load_users()

        # Гарантируем, что пользователь существует и имеет нужные поля
        if session['user'] not in users:
            users[session['user']] = {
                "password": "",
                "photos": [],
                "comments": []
            }

        # Добавляем фото и сохраняем
        users[session['user']]["photos"].append(new_photo)
        save_users(users)

        flash("Фото опубликовано!", "success")
        return redirect(url_for('feed'))

    return render_template("upload.html")

@app.route("/profile")
@login_required
def profile():
    user_photos = [p for p in photos if p['author'] == session['user']]
    user_photos = sorted(user_photos, key=lambda x: x['date'], reverse=True)
    return render_template("profile.html", photos=user_photos)

@app.route("/profile/<username>")
@view_route
def public_profile(username):
    user_photos = [p for p in photos if p['author'] == username]
    user_photos = sorted(user_photos, key=lambda x: x['date'], reverse=True)
    return render_template("public_profile.html", username=username, photos=user_photos)



@app.route("/delete/<int:photo_id>")
@login_required
def delete_photo(photo_id):
    users = load_users()
    user_photos = users[session['user']]["photos"]

    for i, photo in enumerate(user_photos):
        if int(photo['id']) == photo_id:
            # Удаляем файл и запись
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo['filename']))
            del user_photos[i]
            save_users(users)

            flash("Фото удалено!", "success")
            return redirect(url_for('profile'))

    flash("Фото не найдено!", "error")
    return redirect(url_for('profile'))


@app.route("/photo/edit/<int:photo_id>", methods=["GET", "POST"])
@login_required
def edit_photo(photo_id):
    # Найти фото в глобальном списке
    photo = None
    photo_index = -1
    for i, p in enumerate(photos):
        if int(p['id']) == photo_id:
            photo = p
            photo_index = i
            break

    if not photo:
        flash("Фото не найдено!", "error")
        return redirect(url_for('feed'))

    # Проверка: только автор может редактировать
    if photo['author'] != session['user']:
        flash("Вы не можете редактировать это фото!", "error")
        return redirect(url_for('photo_page', photo_id=photo_id))

    if request.method == "POST":
        description = request.form.get('description', '').strip()
        tags_raw = request.form.get('tags', '').strip().lower()
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]

        if not tags:
            flash("Добавьте хотя бы один тег!", "error")
            return render_template("edit_photo.html", photo=photo)

        # Обновляем фото в глобальном списке
        photos[photo_index]['description'] = description
        photos[photo_index]['tags'] = tags

        # Обновляем фото в данных пользователя
        users = load_users()
        user_photos = users[session['user']]["photos"]
        for i, p in enumerate(user_photos):
            if int(p['id']) == photo_id:
                user_photos[i]['description'] = description
                user_photos[i]['tags'] = tags
                break

        save_users(users)

        flash("Фото успешно обновлено!", "success")
        return redirect(url_for('photo_page', photo_id=photo_id))

    return render_template("edit_photo.html", photo=photo)


@app.route("/search")
@view_route
def search():
    query = request.args.get('q', '').strip().lower()
    if not query:
        return redirect(url_for('feed'))

    found_photos = [p for p in photos if query in p['tags']]
    found_photos = sorted(found_photos, key=lambda x: x['date'], reverse=True)
    return render_template("feed.html", photos=found_photos, query=query)


@app.route("/photo/<int:photo_id>", methods=["GET", "POST"])
@view_route  # Заменили login_required на view_route
def photo_page(photo_id):
    photo = None
    for p in photos:
        if int(p['id']) == photo_id:
            photo = p
            break

    if not photo:
        flash("Фото не найдено!", "error")
        return redirect(url_for('feed'))

    # Только авторизованные могут комментировать
    if request.method == "POST" and 'user' in session:
        text = request.form.get('comment').strip()
        parent_id = request.form.get('parent_id', None)
        if text:
            comment_id = str(len(comments) + 1)
            new_comment = {
                "id": comment_id,
                "photo_id": str(photo_id),
                "parent_id": parent_id,
                "author": session['user'],
                "text": text,
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "edited": False
            }
            comments.append(new_comment)

            users = load_users()
            users[session['user']]["comments"].append(new_comment)
            save_users(users)

        return redirect(url_for('photo_page', photo_id=photo_id))

    photo_comments = [c for c in comments if str(c['photo_id']) == str(photo_id)]
    return render_template("photo_page.html", photo=photo, comments=photo_comments)


@app.route("/comment/edit/<comment_id>", methods=["GET", "POST"])
@login_required
def edit_comment(comment_id):
    # Ищем комментарий в общем списке
    comment = None
    comment_index = -1
    for i, c in enumerate(comments):
        if c['id'] == comment_id:
            comment = c
            comment_index = i
            break

    if not comment:
        flash("Комментарий не найден!", "error")
        return redirect(url_for('feed'))

    if comment['author'] != session['user']:
        flash("Вы не можете редактировать этот комментарий!", "error")
        return redirect(url_for('photo_page', photo_id=comment['photo_id']))

    if request.method == "POST":
        new_text = request.form.get('text').strip()
        if new_text:
            # Обновляем комментарий в общем списке
            comment['text'] = new_text
            comment['edited'] = True
            comment['edit_date'] = datetime.now().strftime("%d.%m.%Y %H:%M")
            comments[comment_index] = comment

            # Обновляем комментарий в данных пользователя
            users = load_users()
            user_comments = users[session['user']]["comments"]
            for i, c in enumerate(user_comments):
                if c['id'] == comment_id:
                    user_comments[i] = comment
                    break

            # Сохраняем все изменения
            save_users(users)

            flash("Комментарий отредактирован!", "success")
        return redirect(url_for('photo_page', photo_id=comment['photo_id']))

    return render_template("edit_comment.html", comment=comment)


@app.route("/comment/delete/<comment_id>")
@login_required
def delete_comment(comment_id):
    users = load_users()
    user_comments = users[session['user']]["comments"]
    target_comment = None
    target_index = -1

    for i, c in enumerate(user_comments):
        if c['id'] == comment_id:
            target_comment = c
            target_index = i
            break

    if not target_comment:
        flash("Комментарий не найден!", "error")
        return redirect(url_for('feed'))

    if target_comment['author'] != session['user']:
        flash("Вы не можете удалить этот комментарий!", "error")
        return redirect(url_for('photo_page', photo_id=target_comment['photo_id']))

    # Удаляем комментарий
    del user_comments[target_index]
    save_users(users)

    flash("Комментарий удален!", "success")
    return redirect(url_for('photo_page', photo_id=target_comment['photo_id']))


if __name__ == '__main__':
    # Загружаем данные при запуске
    load_users()

    if not os.path.exists("users.txt"):
        with open("users.txt", "w", encoding="utf-8") as f:
            f.write("user:user1::::\nadmin:admin1::::\n")
    app.run(host='0.0.0.0', port=5000, debug=True)