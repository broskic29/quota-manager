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
            <a href="/admin/group_management">
                <button><i class="fa-solid fa-chart-pie"></i> Manage Groups</button>
            </a>
            <a href="/admin/usage">
                <button><i class="fa-solid fa-chart-pie"></i> Usage Overview</button>
            </a>
        </div>
    </div>
</body>
</html>
"""

group_management_page = """
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
            <a href="/admin/group_management">
                <button><i class="fa-solid fa-chart-pie"></i> Manage Groups</button>
            </a>
            <a href="/admin/usage">
                <button><i class="fa-solid fa-chart-pie"></i> Usage Overview</button>
            </a>
        </div>
    </div>
</body>
</html>
"""
