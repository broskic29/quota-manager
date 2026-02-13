new_user_form = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Create New User</title>

<style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
    }

    .container {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        width: 90%;
        max-width: 400px;
    }

    h2 {
        margin-bottom: 1.5rem;
        text-align: center;
        color: #333;
        font-size: 1.8rem;
    }

    form {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    label {
        display: flex;
        flex-direction: column;
        font-weight: bold;
        color: #555;
    }

    input[type="text"],
    select {
        padding: 0.6rem;
        font-size: 1rem;
        border: 1px solid #ccc;
        border-radius: 8px;
        margin-top: 0.3rem;
    }

    input[type="submit"] {
        padding: 0.9rem;
        font-size: 1.1rem;
        font-weight: bold;
        color: white;
        background-color: #007bff;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: background-color 0.2s ease;
    }

    input[type="submit"]:hover {
        background-color: #0056b3;
    }

    .error-message {
        color: red;
        text-align: center;
        font-weight: bold;
    }
</style>
</head>
<body>
    <div class="container">
        <h2>Create New User</h2>
        <form method="post">
            <label>
                Username:
                <input type="text" name="username" placeholder="Enter username" required>
            </label>

            <label>
                Group:
                {% if groups %}
                    <select name="group_name" required>
                        {% for group in groups %}
                            <option value="{{ group }}">{{ group }}</option>
                        {% endfor %}
                    </select>
                {% else %}
                    <div style="margin-top: 0.5rem; color: #a00; font-size: 0.9rem;">
                        No groups exist yet.
                        <a href="http://192.168.3.1:5001/admin/new_group" style="color: #007bff; text-decoration: none;">
                            Create a group first.
                        </a>
                    </div>
                {% endif %}
            </label>

            <input
                type="submit"
                value="Create User"
                {% if not groups %}disabled style="opacity:0.6; cursor:not-allowed;"{% endif %}>

            <!-- Back link -->
            <div style="margin-top: 1.2rem; text-align: center;">
                <a href="http://192.168.3.1:5001/admin" style="color: #555; text-decoration: none; font-size: 0.9rem;">
                    ← Back to Admin Panel
                </a>
            </div>
        </form>


        {% if error %}
        <p class="error-message">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""

new_group_form = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Create New Group</title>

<style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
    }

    .container {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        width: 90%;
        max-width: 400px;
    }

    h2 {
        margin-bottom: 1.5rem;
        text-align: center;
        color: #333;
        font-size: 1.8rem;
    }

    form {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    label {
        display: flex;
        flex-direction: column;
        font-weight: bold;
        color: #555;
    }

    input[type="text"],
    input[type="number"],
    select {
        padding: 0.6rem;
        font-size: 1rem;
        border: 1px solid #ccc;
        border-radius: 8px;
        margin-top: 0.3rem;
    }

    select {
        width: 40%;
        margin-top: 0.3rem;
    }

    .quota-field {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    input[type="submit"] {
        padding: 0.9rem;
        font-size: 1.1rem;
        font-weight: bold;
        color: white;
        background-color: #007bff;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        transition: background-color 0.2s ease;
    }

    input[type="submit"]:hover {
        background-color: #0056b3;
    }

    .error-message {
        color: red;
        text-align: center;
        font-weight: bold;
    }
</style>
</head>
<body>
    <div class="container">
        <h2>Create New Group</h2>
        <form method="post">
            <label>
                Group Name:
                <input type="text" name="group_name" placeholder="Enter group name" required>
            </label>

            <label>
                Desired Quota Ratio:
                <div class="quota-field">
                    <input
                        type="number"
                        name="desired_quota_ratio"
                        min="0"
                        max="1"
                        step="0.01"
                        required
                    >
                </div>
                <small style="display:block; color:#555; font-size:0.9em;">
                </small>
            </label>

            <input type="submit" value="Create Group">

            <div style="margin-top: 1.5rem; text-align: center;">
                <a href="http://192.168.3.1:5001/admin" style="color: #007bff; text-decoration: none; font-size: 0.95rem;">
                    ← Back to Admin Panel
                </a>
            </div>
        </form>

        {% if error %}
        <p class="error-message">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""

success_page = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Success</title>

<style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: #f4f6f8;
        margin: 0;
        min-height: 100vh;
        display: flex;
        justify-content: center;
        align-items: center;
    }

    .container {
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        text-align: center;
        width: 90%;
        max-width: 400px;
    }

    h2 {
        color: #2d7a2d;
        margin-bottom: 1rem;
    }

    p {
        color: #444;
        margin-bottom: 2rem;
        font-size: 1rem;
    }

    a.button {
        display: inline-block;
        padding: 0.75rem 1.25rem;
        background-color: #007bff;
        color: white;
        text-decoration: none;
        font-weight: bold;
        border-radius: 8px;
        transition: background-color 0.2s ease;
    }

    a.button:hover {
        background-color: #0056b3;
    }
</style>
</head>
<body>
    <div style="margin-top: 1.5rem; text-align: center;">
        <p>{{ message }}</p>
        <a href="http://192.168.3.1:5001/admin" style="color: #007bff; text-decoration: none; font-size: 0.95rem;">
            ← Back to Admin Panel
        </a>
    </div>
</body>
</html>
"""


admin_landing_page = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Panel</title>

<!-- Font Awesome for icons -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" integrity="sha512-..." crossorigin="anonymous" referrerpolicy="no-referrer" />

<style>
    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
    }

    .container {
        text-align: center;
        background: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        width: 90%;
        max-width: 400px;
    }

    h1 {
        margin-bottom: 2rem;
        color: #333;
        font-size: 2rem;
    }

    .button-grid {
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }

    .button-grid a {
        text-decoration: none;
    }

    .button-grid button {
        width: 100%;
        padding: 1rem;
        font-size: 1rem;
        font-weight: bold;
        color: white;
        background-color: #007bff;
        border: none;
        border-radius: 8px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.5rem;
        transition: background-color 0.2s ease;
    }

    .button-grid button:hover {
        background-color: #0056b3;
    }

    .button-grid button {
        flex-direction: column;
    }

    @media (min-width: 500px) {
        .button-grid button {
            flex-direction: row;
        }
    }

</style>
</head>
<body>
    <div class="container">
        <h1>Admin Panel</h1>
        <div class="button-grid">
            <a href="/admin/new_user">
                <button><i class="fa-solid fa-user-plus"></i> Create User</button>
            </a>
            <a href="/admin/new_group">
                <button><i class="fa-solid fa-users"></i> Create Group</button>
            </a>
            <a href="/admin/usage">
                <button><i class="fa-solid fa-chart-pie"></i> Usage Overview</button>
            </a>
            <a href="/admin/users">
                <button><i class="fa-solid fa-user-gear"></i> Manage Users</button>
            </a>
            <a href="/admin/groups">
                <button><i class="fa-solid fa-users-gear"></i> Manage Groups</button>
            </a>
            <a href="/admin/config">
                <button><i class="fa-solid fa-sliders"></i> System Config</button>
            </a>
            <form method="post" action="/admin/reset"
                  onsubmit="return confirm('This action will delete all user information. Are you sure you want to reset?');">
                <button type="submit" class="danger">
                    <i class="fa-solid fa-triangle-exclamation"></i> Reset System
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""


manage_users_page = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Manage Users</title>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" integrity="sha512-..." crossorigin="anonymous" referrerpolicy="no-referrer" />

<style>
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 0;
    background: #f4f6f8;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-height: 100vh;
  }

  .container {
    background: white;
    padding: 2rem;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    width: 90%;
    max-width: 650px;
    margin: 2rem 0;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  h1 {
    margin: 0;
    font-size: 2rem;
    color: #333;
  }

  .back-link {
    text-decoration: none;
    color: #007bff;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .back-link:hover {
    text-decoration: underline;
  }

  .card {
    border: 1px solid #e6e9ee;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #fff;
  }

  .user-name {
    font-weight: 600;
    color: #222;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  button {
    padding: 0.6rem 0.9rem;
    font-size: 0.95rem;
    font-weight: bold;
    color: white;
    background-color: #007bff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    transition: background-color 0.2s ease;
  }

  button:hover {
    background-color: #0056b3;
  }

  .danger {
    background-color: #dc3545;
  }

  .danger:hover {
    background-color: #b52a37;
  }

  .empty {
    text-align: center;
    color: #777;
    padding: 2rem 0;
  }

    select {
    padding: 0.55rem 0.7rem;
    border-radius: 8px;
    border: 1px solid #d5dbe3;
    background: white;
    font-weight: 600;
    color: #222;
    }

</style>
</head>

<body>
  <div class="container">

    <div class="header">
      <h1>Manage Users</h1>
      <a class="back-link" href="/admin">
        <i class="fa-solid fa-arrow-left"></i> Back
      </a>
    </div>

    {% if users %}
        {% for u in users %}
        <div class="card">
            <div class="user-name">
            <i class="fa-solid fa-user"></i>
            {{ u.username }}
            </div>

            <div style="display:flex; gap: 0.5rem; align-items:center;">
            <form method="post" action="/admin/users/{{ u.username }}/group">
                <select name="group_name" onchange="this.form.submit()">
                {% for g in groups %}
                    <option value="{{ g }}" {% if u.group_name == g %}selected{% endif %}>
                    {{ g }}
                    </option>
                {% endfor %}
                </select>
            </form>

            <form method="post" action="/admin/users/{{ u.username }}/delete">
                <button
                class="danger"
                type="submit"
                onclick="return confirm('Delete user {{u.username}}?')"
                >
                <i class="fa-solid fa-trash"></i> Delete
                </button>
            </form>
            </div>
        </div>
        {% endfor %}
    {% else %}
      <div class="empty">No users found.</div>
    {% endif %}

  </div>
</body>
</html>
"""


manage_groups_page = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Manage Groups</title>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" integrity="sha512-..." crossorigin="anonymous" referrerpolicy="no-referrer" />

<style>
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 0;
    background: #f4f6f8;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-height: 100vh;
  }

  .container {
    text-align: left;
    background: white;
    padding: 2rem;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    width: 90%;
    max-width: 650px;
    margin: 2rem 0;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  h1 {
    margin: 0;
    color: #333;
    font-size: 2rem;
  }

  .back-link {
    text-decoration: none;
    color: #007bff;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .back-link:hover {
    text-decoration: underline;
  }

  .card {
    border: 1px solid #e6e9ee;
    border-radius: 12px;
    padding: 1rem;
    margin: 0.75rem 0;
    background: #fff;
  }

  .card-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .card-title b {
    font-size: 1.1rem;
    color: #222;
  }

  .meta {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem 1rem;
    margin-bottom: 0.75rem;
    color: #444;
  }

  .meta div {
    background: #f8fafc;
    border: 1px solid #eef2f7;
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
  }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .form-row {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
  }

  input[type="number"] {
    flex: 1;
    min-width: 180px;
    padding: 0.75rem;
    border: 1px solid #d7dce3;
    border-radius: 8px;
    font-size: 1rem;
  }

  input[type="number"]:focus {
    outline: none;
    border-color: #007bff;
    box-shadow: 0 0 0 3px rgba(0,123,255,0.15);
  }

  button {
    padding: 0.75rem 1rem;
    font-size: 1rem;
    font-weight: bold;
    color: white;
    background-color: #007bff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    transition: background-color 0.2s ease;
  }

  button:hover {
    background-color: #0056b3;
  }

  .danger {
    background-color: #dc3545;
  }

  .danger:hover {
    background-color: #b52a37;
  }

  .hint {
    color: #666;
    font-size: 0.9rem;
    margin-top: -0.25rem;
  }

  @media (min-width: 500px) {
    .actions {
      flex-direction: row;
      justify-content: space-between;
      align-items: flex-start;
    }
    .actions form {
      flex: 1;
    }
    .meta {
      grid-template-columns: 1fr 1fr;
    }
  }

  @media (max-width: 499px) {
    .meta {
      grid-template-columns: 1fr;
    }
    button {
      width: 100%;
    }
  }
</style>
</head>

<body>
  <div class="container">
    <div class="header">
      <h1>Manage Groups</h1>
      <a class="back-link" href="/admin"><i class="fa-solid fa-arrow-left"></i> Back</a>
    </div>

    {% for g in groups %}
      <div class="card">
        <div class="card-title">
          <b><i class="fa-solid fa-users-gear"></i> {{ g.group_name }}</b>
        </div>

        <div class="meta">
          <div><b>Desired ratio:</b> {{ g.desired_quota_ratio }}</div>
          <div><b>Members:</b> {{ g.num_members }}</div>
        </div>

        <div class="actions">
          <form method="post" action="/admin/groups/{{ g.group_name }}/ratio">
            <div class="form-row">
              <input
                type="number"
                name="desired_quota_ratio"
                min="0"
                max="1"
                step="0.01"
                required
                value="{{ g.desired_quota_ratio }}"
              >
              <button type="submit"><i class="fa-solid fa-rotate"></i> Update ratio</button>
            </div>
          </form>

          <form method="post" action="/admin/groups/{{ g.group_name }}/delete">
            <button
              class="danger"
              type="submit"
              onclick="return confirm('Delete group {{g.group_name}}? (must be empty)')"
            >
              <i class="fa-solid fa-trash"></i> Delete group
            </button>
          </form>
        </div>
      </div>
    {% endfor %}
  </div>
</body>
</html>
"""


config_page = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>System Config</title>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" integrity="sha512-..." crossorigin="anonymous" referrerpolicy="no-referrer" />

<style>
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 0;
    background: #f4f6f8;
    display: flex;
    justify-content: center;
    align-items: flex-start;
    min-height: 100vh;
  }

  .container {
    background: white;
    padding: 2rem;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    width: 90%;
    max-width: 650px;
    margin: 2rem 0;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

  h1 {
    margin: 0;
    font-size: 2rem;
    color: #333;
  }

  .back-link {
    text-decoration: none;
    color: #007bff;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .back-link:hover {
    text-decoration: underline;
  }

  .card {
    border: 1px solid #e6e9ee;
    border-radius: 12px;
    padding: 1rem;
    background: #fff;
    margin-bottom: 0.9rem;
  }

  .section-title {
    font-weight: 700;
    color: #222;
    margin-bottom: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .row {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.9rem;
  }

  label {
    font-weight: 600;
    color: #333;
  }

  .hint {
    font-size: 0.9rem;
    color: #666;
    font-weight: 500;
  }

  input[type="number"],
  input[type="text"] {
    padding: 0.65rem 0.75rem;
    border-radius: 10px;
    border: 1px solid #d5dbe3;
    font-size: 1rem;
    outline: none;
    transition: border-color 0.15s ease;
  }

  input[type="number"]:focus,
  input[type="text"]:focus {
    border-color: #007bff;
  }

  .toggle-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.65rem 0.75rem;
    border: 1px solid #e6e9ee;
    border-radius: 12px;
    background: #fafbfc;
    margin-bottom: 0.9rem;
  }

  .toggle-row .left {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  input[type="checkbox"] {
    transform: scale(1.2);
    accent-color: #007bff;
  }

  .days {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.4rem;
  }

  .day-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.45rem 0.65rem;
    border: 1px solid #e6e9ee;
    border-radius: 999px;
    background: #fafbfc;
    font-weight: 600;
    color: #333;
    user-select: none;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 1rem;
  }

  button {
    padding: 0.6rem 0.9rem;
    font-size: 0.95rem;
    font-weight: bold;
    color: white;
    background-color: #007bff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    transition: background-color 0.2s ease;
  }

  button:hover {
    background-color: #0056b3;
  }
</style>
</head>

<body>
  <div class="container">

    <div class="header">
      <h1>System Config</h1>
      <a class="back-link" href="/admin">
        <i class="fa-solid fa-arrow-left"></i> Back
      </a>
    </div>

    <form method="post">

      <div class="card">
        <div class="section-title">
          <i class="fa-solid fa-database"></i> Bandwidth & Policy
        </div>

        <div class="row">
          <label for="total_gb">Total monthly bytes purchased (GB)</label>
          <div class="hint">Used to compute available bandwidth and downstream quotas.</div>
          <input id="total_gb" type="number" name="total_gb" min="0" step="1" value="{{ total_gb }}" required>
        </div>

        <div class="toggle-row">
          <div class="left">
            <div style="font-weight:700; color:#222;">Throttling enabled</div>
            <div class="hint">If enabled, users may be rate-limited after quota use.</div>
          </div>
          <input type="checkbox" name="throttling_enabled" value="1" {% if throttling_enabled %}checked{% endif %}>
        </div>

        <div class="row">
          <label>Active days (0=Mon .. 6=Sun)</label>
          <div class="hint">These days count as “system active” for quota calculations.</div>
          <div class="days">
            {% for d in range(7) %}
              <label class="day-pill">
                <input type="checkbox" name="active_days" value="{{d}}" {% if d in active_days %}checked{% endif %}>
                {{ d }}
              </label>
            {% endfor %}
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">
          <i class="fa-solid fa-shield-halved"></i> MAC Restrictions
        </div>

        <div class="toggle-row">
          <div class="left">
            <div style="font-weight:700; color:#222;">MAC set limitation enabled</div>
            <div class="hint">If enabled, only explicitly allowed MACs may authenticate.</div>
          </div>
          <input type="checkbox" name="mac_set_limitation" value="1" {% if mac_set_limitation %}checked{% endif %}>
        </div>

        <div class="row">
          <label for="allowed_macs">Allowed MACs (comma separated)</label>
          <div class="hint">Example: <code>aa:bb:cc:dd:ee:ff, 11:22:33:44:55:66</code></div>
          <input id="allowed_macs" type="text" name="allowed_macs" value="{{ allowed_macs }}">
        </div>
      </div>

      <div class="actions">
        <button type="submit">
          <i class="fa-solid fa-floppy-disk"></i> Save
        </button>
      </div>

    </form>

  </div>
</body>
</html>
"""
