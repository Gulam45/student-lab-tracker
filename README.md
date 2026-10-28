# Student Lab & Attendance Tracker

A standalone, menu-driven command-line application for managing student
records, daily attendance, and lab component marks. Data is stored locally in
SQLite, and student summaries can be exported to CSV. The project uses only
Python's standard library.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Getting started

Open a terminal in the project directory and run:

```powershell
python student_tracker.py
```

The application creates `student_tracker.db` in the current working directory
if the database does not already exist. To use a different database file:

```powershell
python student_tracker.py --database "data\students.db"
```

The parent directory is created automatically when needed. The database
persists between runs.

## Menu options

1. **Add student** — save a student's USN, name, and semester. USNs are unique
   and stored uppercase.
2. **Mark daily attendance** — record `Present` or `Absent` for a student and
   date. If a record for that student and date already exists, its attendance
   status is updated.
3. **Enter lab component marks** — save a mark from 0 to 100 for an existing
   attendance record.
4. **Calculate attendance percentage** — display the student's percentage.
5. **Export student summary to CSV** — write a report to the path you enter.
6. **List students** — display the students currently in the database.
0. **Exit**

The menu validates input and reports errors such as duplicate USNs, unknown
students, invalid dates, and out-of-range marks.

## Data and calculations

- `Students` stores each student's USN, name, and semester.
- `Attendance` stores one record per student per date, with status and an
  optional lab mark. Deleting a student through the database also removes that
  student's attendance records.
- Dates must use the `YYYY-MM-DD` format.
- Attendance percentage is `Present` records divided by all recorded
  attendance records, multiplied by 100. A student with no attendance records
  has a percentage of 0%.
- Lab marks are optional. The CSV's average lab mark is calculated from marks
  that have been entered; if none have been entered, the field is blank.

## CSV report

The export writes one row per student with these columns:

- USN
- Name
- Semester
- Attendance Sessions
- Present Sessions
- Attendance Percentage
- Average Lab Marks

The report is saved to the path entered in the menu. For example, enter
`reports\student_summary.csv` to create the report in a `reports` folder.
