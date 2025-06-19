import sqlite3

# Connect to the database
conn = sqlite3.connect('job_screening.db')
cursor = conn.cursor()

# Query to select all candidates
cursor.execute("SELECT * FROM Candidates")

# Fetch all results
candidates = cursor.fetchall()

# Print the results
for candidate in candidates:
    print(candidate)

# Close the connection
conn.close()
