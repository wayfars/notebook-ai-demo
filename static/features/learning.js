(() => {
  'use strict';

  const API = '/learn/api';
  const state = { user: null, csrf: '', dashboard: null, directory: [], users: [], section: 'overview', courseId: '', detail: null, childId: '', learnerId: '', draft: null };
  const $ = (selector, root = document) => root.querySelector(selector);
  const viewLogin = $('#login-view');
  const viewWorkspace = $('#workspace-view');
  const content = $('#section-content');
  const nav = $('#section-nav');

  function make(tag, options = {}, children = []) {
    const item = document.createElement(tag);
    if (options.className) item.className = options.className;
    if (options.text !== undefined) item.textContent = String(options.text);
    if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) {
      if (value !== undefined && value !== null) item.setAttribute(key, String(value));
    }
    for (const child of children) if (child) item.append(child);
    return item;
  }
  const text = (tag, value, cls) => make(tag, { text: value ?? '', className: cls });
  const card = (title, subtitle) => {
    const section = make('section', { className: 'card' });
    const head = make('div', { className: 'card-head' }, [make('div', {}, [text('h2', title), ...(subtitle ? [text('p', subtitle, 'muted')] : [])])]);
    section.append(head);
    return section;
  };
  const isObj = value => value && typeof value === 'object' && !Array.isArray(value);
  const rows = value => Array.isArray(value) ? value : [];
  const labelRole = role => ({ teacher: 'Teacher', student: 'Student', parent: 'Parent', tutor: 'Tutor' }[role] || 'Learning member');
  const displayName = person => person?.display_name || person?.username || 'Learner';
  const courseName = course => course?.title || 'Course';
  const assignmentName = assignment => assignment?.title || 'Assignment';
  const asText = value => typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));

  function setNotice(message = '', error = false) {
    const notice = $('#notice');
    notice.textContent = message;
    notice.classList.toggle('error', Boolean(error));
    notice.hidden = !message;
  }
  function setStatus(message = '') { $('#workspace-status').textContent = message; }
  function setLoginMessage(message = '') { $('#login-message').textContent = message; }
  function empty(title, message) {
    const box = make('div', { className: 'empty-state' });
    box.append(text('strong', title), text('p', message));
    return box;
  }
  function appendItems(parent, items, emptyTitle, emptyMessage, renderer) {
    const list = make('ul', { className: 'list' });
    if (!items.length) parent.append(empty(emptyTitle, emptyMessage));
    else { for (const item of items) list.append(renderer(item)); parent.append(list); }
  }
  function shortDate(value) {
    if (!value) return 'No due date';
    const date = new Date(`${value}T12:00:00`);
    return Number.isNaN(date.valueOf()) ? asText(value) : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
  }
  function formatPercent(value) { return finite(value) ? `${Math.round(Number(value))}%` : 'No published grades yet'; }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    if (options.auth !== false && options.method && options.method !== 'GET') headers.set('X-CSRF-Token', state.csrf);
    const response = await fetch(`${API}${path}`, {
      method: options.method || 'GET', credentials: 'same-origin', headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    let data = {};
    try { data = await response.json(); } catch { /* An empty response has no details to show. */ }
    if (!response.ok) {
      if (response.status === 401 && options.auth !== false) showLogin();
      throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status}).`);
    }
    return data;
  }
  async function mutate(path, method, body, successMessage, after = true) {
    setNotice('Saving…');
    try {
      await api(path, { method, body });
      if (after) await refreshDashboard();
      setNotice(successMessage);
      renderCurrent();
      return true;
    } catch (error) { setNotice(error.message || 'Could not save. Please try again.', true); return false; }
  }
  async function refreshDashboard() {
    state.dashboard = await api('/dashboard');
    if (state.user?.role === 'teacher') {
      const directory = await api('/directory');
      state.directory = Array.isArray(directory) ? directory : rows(directory.users);
    }
    if (state.user?.role === 'teacher' && state.user?.is_admin) {
      const users = await api('/users');
      state.users = Array.isArray(users) ? users : rows(users.users);
    }
    const courses = rows(state.dashboard.courses);
    if (!courses.some(course => String(course.id) === String(state.courseId))) state.courseId = courses[0] ? String(courses[0].id) : '';
    if (state.courseId && ['courses', 'assignments', 'practice', 'learning'].includes(state.section)) await loadCourse(state.courseId);
  }
  async function loadCourse(id) {
    if (!id) { state.detail = null; return; }
    state.courseId = String(id);
    try { state.detail = await api(`/courses/${encodeURIComponent(id)}`); }
    catch (error) { state.detail = null; setNotice(error.message, true); }
  }
  function showLogin(message = '') {
    state.user = null; state.csrf = ''; state.dashboard = null;
    viewLogin.hidden = false; viewWorkspace.hidden = true; $('#account-area').hidden = true;
    setLoginMessage(message);
    $('#login-username').focus({ preventScroll: true });
  }
  async function showWorkspace(user, csrf) {
    state.user = user; state.csrf = csrf || '';
    $('#account-area').hidden = false;
    $('#account-name').textContent = displayName(user);
    $('#account-role').textContent = labelRole(user.role);
    viewLogin.hidden = true; viewWorkspace.hidden = false;
    $('#welcome-title').textContent = `Welcome, ${displayName(user)}`;
    $('#welcome-eyebrow').textContent = `${labelRole(user.role)} workspace`;
    $('#welcome-copy').textContent = welcomeCopy(user.role);
    state.section = 'overview';
    try { await refreshDashboard(); renderCurrent(); }
    catch (error) { setNotice(error.message || 'Could not load your learning workspace.', true); }
  }
  function welcomeCopy(role) {
    return ({
      teacher: 'Plan lessons, support your students, and review submitted work.',
      student: 'Open a course, work through a lesson, and ask questions as you study.',
      parent: 'Follow the published grades and topic progress for your linked children.',
      tutor: 'See your assigned learners and prepare focused practice for their next step.',
    })[role] || 'Your courses and learning activity will appear here.';
  }

  function sectionsFor(role) {
    if (role === 'teacher') return [['overview', 'Overview'], ['courses', 'Courses'], ['assignments', 'Assignments'], ...(state.user?.is_admin ? [['people', 'People']] : [])];
    if (role === 'student') return [['overview', 'Overview'], ['learning', 'My learning'], ['profile', 'Study preference']];
    if (role === 'parent') return [['overview', 'Overview'], ['children', 'Children']];
    if (role === 'tutor') return [['overview', 'Overview'], ['learners', 'Assigned learners'], ['practice', 'Practice studio']];
    return [['overview', 'Overview']];
  }
  function renderNav() {
    nav.replaceChildren();
    for (const [id, label] of sectionsFor(state.user.role)) {
      const button = make('button', { className: 'nav-button', text: label, attrs: { type: 'button', 'aria-current': state.section === id ? 'page' : 'false' } });
      button.addEventListener('click', async () => {
        state.section = id; setNotice('');
        if (['courses', 'assignments', 'practice', 'learning'].includes(id)) await loadCourse(state.courseId);
        renderCurrent();
      });
      nav.append(button);
    }
  }
  function renderCurrent() {
    if (!state.user || !state.dashboard) return;
    renderNav(); content.replaceChildren();
    const renderers = {
      overview: renderOverview,
      courses: renderTeacherCourses,
      assignments: renderAssignments,
      people: renderPeople,
      learning: renderStudentLearning,
      profile: renderPreference,
      children: renderChildren,
      learners: renderTutorLearners,
      practice: renderPractice,
    };
    (renderers[state.section] || renderOverview)();
  }
  function stat(title, value, note) {
    const box = make('section', { className: 'card span-4' });
    box.append(text('span', value, 'stat-value'), text('span', title, 'stat-label'));
    if (note) box.append(text('p', note, 'muted'));
    return box;
  }
  function metricCard(title, value, explanation) {
    const box = make('section', { className: 'card' });
    box.append(text('h3', title), text('span', value, 'stat-value'), text('p', explanation, 'muted'));
    return box;
  }
  function renderOverview() {
    const dashboard = state.dashboard;
    const courses = rows(dashboard.courses), students = rows(dashboard.students), assignments = rows(dashboard.assignments), progress = rows(dashboard.progress);
    const grid = make('div', { className: 'grid' });
    grid.append(stat('Courses', courses.length, 'Courses available to you'));
    if (state.user.role === 'teacher') grid.append(stat('Students', students.length, 'Learners in your workspace'));
    else if (state.user.role === 'parent') grid.append(stat('Linked children', students.length, 'Children connected to your account'));
    else if (state.user.role === 'tutor') grid.append(stat('Assigned learners', students.length, 'Students you are assigned to support'));
    else grid.append(stat('Assignments', assignments.length, 'Course work in your learning space'));
    if (state.user.role === 'parent') grid.append(stat('Progress reports', progress.length, 'Reports with published learning evidence'));
    else if (state.user.role === 'teacher') grid.append(stat('Assignments', assignments.length, 'Official and practice work'));
    else if (state.user.role === 'student') grid.append(stat('Published grades', assignments.filter(a => finite(a.points)).length, 'Grades that have been shared with you'));
    else grid.append(stat('Practice tasks', assignments.filter(a => a.kind === 'practice').length, 'Targeted practice in assigned courses'));
    content.append(grid);

    const courseCard = card('Your courses', 'Choose a course to open its lessons and assignments.');
    appendItems(courseCard, courses, 'No courses yet', 'When a course is shared with you, it will be listed here.', course => {
      const li = make('li', { className: 'list-row' });
      const title = make('button', { className: 'button button-secondary', text: courseName(course), attrs: { type: 'button' } });
      title.addEventListener('click', async () => { state.courseId = String(course.id); state.section = state.user.role === 'student' ? 'learning' : state.user.role === 'teacher' ? 'courses' : state.user.role === 'tutor' ? 'practice' : 'children'; await loadCourse(state.courseId); renderCurrent(); });
      li.append(title); if (course.description) li.append(text('p', course.description, 'muted'));
      return li;
    });
    content.append(courseCard);
    const assignmentsCard = card(state.user.role === 'student' ? 'Course work' : 'Recent course work', 'Only published grades are shown to learners and linked parents.');
    appendItems(assignmentsCard, assignments.slice(0, 6), 'Nothing assigned yet', 'Assignments will appear here when a teacher or tutor shares them.', assignment => assignmentRow(assignment, state.user.role));
    content.append(assignmentsCard);
    if (state.user.role === 'parent' && students.length) content.append(renderProgressPicker(students));
  }
  function assignmentRow(assignment, role) {
    const li = make('li', { className: 'list-row' });
    li.append(text('strong', assignmentName(assignment)));
    li.append(text('p', assignment.instructions || 'Instructions will appear in the assignment.', 'muted'));
    const meta = make('div', { className: 'meta' });
    meta.append(make('span', { className: 'tag', text: assignment.course_title || 'Course' }));
    if (assignment.topic) meta.append(make('span', { className: 'tag', text: assignment.topic }));
    meta.append(make('span', { className: 'tag', text: assignment.kind === 'practice' ? 'Practice' : 'Official' }));
    if (role === 'student') meta.append(make('span', { className: 'tag', text: assignment.submitted ? 'Submitted' : 'To do' }));
    if (role !== 'student' && assignment.target_student_id) meta.append(make('span', { className: 'tag pink', text: `Targeted to ${assignment.target_student_name || 'one learner'}` }));
    if (role === 'student' || role === 'parent' || role === 'tutor') {
      if (finite(assignment.points)) meta.append(make('span', { className: 'tag', text: `Grade ${assignment.points}/${assignment.max_points}` }));
      else if (assignment.submitted) meta.append(make('span', { className: 'tag', text: 'Awaiting grade' }));
    }
    meta.append(make('span', { text: shortDate(assignment.due_date) }));
    li.append(meta);
    if (assignment.feedback && assignment.published) li.append(text('p', `Feedback: ${assignment.feedback}`));
    return li;
  }

  function selectField(form, name, labelText, options, value = '') {
    const id = `${name}-${Math.random().toString(36).slice(2, 8)}`;
    const label = make('label', { text: labelText, attrs: { for: id } });
    const select = make('select', { attrs: { id, name, required: 'required' } });
    select.append(make('option', { text: 'Choose…', attrs: { value: '' } }));
    for (const option of options) {
      const opt = make('option', { text: option.label, attrs: { value: option.value } });
      if (String(option.value) === String(value)) opt.selected = true;
      select.append(opt);
    }
    const wrapper = make('div', {}, [label, select]); form.append(wrapper); return select;
  }
  function field(form, name, labelText, options = {}) {
    const id = `${name}-${Math.random().toString(36).slice(2, 8)}`;
    const label = make('label', { text: labelText, attrs: { for: id } });
    const isTextarea = options.type === 'textarea';
    const control = make(isTextarea ? 'textarea' : 'input', { attrs: { id, name, ...(isTextarea ? {} : { type: options.type || 'text' }), maxlength: options.maxLength || 240, ...(options.minLength ? { minlength: options.minLength } : {}), ...(options.required ? { required: 'required' } : {}), ...(options.min !== undefined ? { min: options.min } : {}), ...(options.max !== undefined ? { max: options.max } : {}), ...(options.step ? { step: options.step } : {}), ...(options.placeholder ? { placeholder: options.placeholder } : {}) } });
    if (options.value !== undefined) control.value = String(options.value);
    if (options.className) control.className = options.className;
    const wrapper = make('div'); wrapper.append(label, control); form.append(wrapper); return control;
  }
  function formFor(title, specs, submitText, onSubmit, className = 'stack-form') {
    const form = make('form', { className, attrs: { novalidate: '' } });
    form.append(text('h3', title));
    const controls = {};
    for (const spec of specs) controls[spec.name] = spec.options?.choices ? selectField(form, spec.name, spec.label, spec.options.choices, spec.options.value) : field(form, spec.name, spec.label, spec.options || {});
    const submit = make('button', { className: 'button button-primary', text: submitText, attrs: { type: 'submit' } });
    form.append(submit);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const values = {};
      for (const spec of specs) {
        const raw = controls[spec.name].value;
        const value = spec.name === 'password' ? raw : raw.trim();
        if (spec.options?.required && !value) { controls[spec.name].focus(); return; }
        if (spec.options?.maxLength && value.length > spec.options.maxLength) { controls[spec.name].setCustomValidity(`Use ${spec.options.maxLength} characters or fewer.`); controls[spec.name].reportValidity(); controls[spec.name].setCustomValidity(''); return; }
        values[spec.name] = value;
      }
      submit.disabled = true;
      try { await onSubmit(values); } catch (error) { setNotice(error.message || 'Could not complete this action.', true); }
      finally { submit.disabled = false; }
    });
    return { form, controls };
  }
  function labelOptions(rows, label = displayName, key = item => item.id) { return rows.map(item => ({ value: key(item), label: label(item) })); }
  function coursePicker(container, allCourses = rows(state.dashboard.courses), onChange = async id => { await loadCourse(id); renderCurrent(); }) {
    if (!allCourses.length) { container.append(empty('No course available', 'A course will appear here after it is created or shared with you.')); return null; }
    const picker = make('div', { className: 'card span-12' });
    const select = selectField(picker, 'active-course', 'Course', labelOptions(allCourses, courseName), state.courseId);
    select.addEventListener('change', async () => { state.courseId = select.value; await onChange(select.value); });
    container.append(picker);
    return picker;
  }
  function courseData() { return state.detail?.course || rows(state.dashboard.courses).find(course => String(course.id) === state.courseId) || null; }
  function lessons() { return rows(state.detail?.lessons); }
  function assignments() {
    const summaries = new Map(rows(state.dashboard?.assignments).map(item => [String(item.id), item]));
    return rows(state.detail?.assignments).map(item => {
      const summary = summaries.get(String(item.id));
      if (!summary) return item;
      return { ...item, ...summary };
    });
  }
  function studentsInCourse() { return rows(state.detail?.students); }
  function tutorsInCourse() { return rows(state.detail?.tutors); }
  function sectionGrid() { return make('div', { className: 'grid' }); }

  function renderTeacherCourses() {
    const courses = rows(state.dashboard.courses), grid = sectionGrid();
    const createCard = card('Create a course', 'Start with a course your students can access.');
    const creation = formFor('Course details', [
      { name: 'title', label: 'Course title', options: { required: true, maxLength: 120 } },
      { name: 'description', label: 'Description', options: { type: 'textarea', maxLength: 2000 } },
    ], 'Create course', async values => {
      setNotice('Creating course…');
      try {
        const result = await api('/courses', { method: 'POST', body: values });
        await refreshDashboard(); if (result?.course?.id || result?.id) state.courseId = String(result.course?.id || result.id);
        await loadCourse(state.courseId); setNotice('Course created. Add learners and lessons when you are ready.'); renderCurrent();
      } catch (error) { setNotice(error.message, true); }
    });
    createCard.append(creation.form); grid.append(createCard);
    const manage = card('Manage a course', 'Enroll students and assign tutors to a course you own.');
    coursePicker(manage);
    const current = courseData();
    if (current) {
      manage.append(text('p', current.description || 'No course description yet.', 'muted'));
      const memberRow = make('div', { className: 'two-column' });
      const allStudents = state.directory.filter(person => person.role === 'student');
      const enrolledIds = new Set(studentsInCourse().map(person => String(person.id)));
      const availableStudents = allStudents.filter(person => !enrolledIds.has(String(person.id)));
      if (allStudents.length) {
        if (availableStudents.length) {
          const enroll = formFor('Enroll student', [{ name: 'student_id', label: 'Student', options: { required: true, choices: labelOptions(availableStudents) } }], 'Enroll student', values => mutate(`/courses/${encodeURIComponent(state.courseId)}/enrollments`, 'POST', values, 'Student enrolled.'));
        memberRow.append(enroll.form);
        }
        const tutorChoices = state.directory.filter(p => p.role === 'tutor');
        const enrolledStudents = studentsInCourse();
        if (tutorChoices.length && enrolledStudents.length) {
          const tutor = formFor('Assign tutor', [
            { name: 'student_id', label: 'Student', options: { required: true, choices: labelOptions(enrolledStudents) } },
            { name: 'tutor_id', label: 'Tutor', options: { required: true, choices: labelOptions(tutorChoices) } },
          ], 'Assign tutor', values => mutate(`/courses/${encodeURIComponent(state.courseId)}/tutors`, 'POST', values, 'Tutor assignment saved.'));
          memberRow.append(tutor.form);
        }
      } else memberRow.append(empty('No students available', 'Create student accounts in People before enrolling them.'));
      manage.append(memberRow);
      manage.append(text('h3', `Lessons (${lessons().length})`, 'subsection'));
      appendItems(manage, lessons(), 'No lessons yet', 'Create a lesson below. Its content will be available to enrolled learners.', lessonRow);
      const lesson = formFor('Create a lesson', [
        { name: 'title', label: 'Lesson title', options: { required: true, maxLength: 140 } },
        { name: 'topic', label: 'Topic', options: { required: true, maxLength: 100 } },
        { name: 'learning_objectives', label: 'Learning objectives', options: { type: 'textarea', maxLength: 1600 } },
        { name: 'content', label: 'Lesson content', options: { type: 'textarea', required: true, maxLength: 12000 } },
      ], 'Save lesson', values => mutate(`/courses/${encodeURIComponent(state.courseId)}/lessons`, 'POST', values, 'Lesson saved.'));
      manage.append(lesson.form);
    }
    grid.append(manage); content.append(grid);
  }
  function lessonRow(lesson) {
    const li = make('li', { className: 'list-row' });
    li.append(text('strong', lesson.title || 'Lesson'));
    if (lesson.topic) li.append(make('div', { className: 'meta' }, [make('span', { className: 'tag', text: lesson.topic })]));
    if (lesson.learning_objectives) li.append(text('p', lesson.learning_objectives));
    li.append(text('p', lesson.content || '', 'content-block'));
    return li;
  }

  function renderAssignments() {
    const grid = sectionGrid(); coursePicker(grid);
    const course = courseData();
    if (!course) { content.append(grid); return; }
    const create = card('Create assignment', 'Create official course work for enrolled students.');
    const lessonsList = lessons();
    const options = [{ value: '', label: 'No linked lesson' }, ...labelOptions(lessonsList, lesson => lesson.title)];
    const createForm = formFor('Assignment details', [
      { name: 'title', label: 'Title', options: { required: true, maxLength: 140 } },
      { name: 'instructions', label: 'Instructions', options: { required: true, type: 'textarea', maxLength: 6000 } },
      { name: 'topic', label: 'Topic', options: { required: true, maxLength: 100 } },
      { name: 'lesson_id', label: 'Related lesson', options: { choices: options } },
      { name: 'max_points', label: 'Maximum points', options: { required: true, type: 'number', min: 0.01, max: 100000, step: 'any', value: '10' } },
      { name: 'due_date', label: 'Due date', options: { type: 'date' } },
    ], 'Create official assignment', async values => {
      if (!finite(values.max_points) || Number(values.max_points) <= 0) throw new Error('Maximum points must be a positive number.');
      const body = { ...values, max_points: Number(values.max_points), kind: 'official' };
      if (!body.lesson_id) delete body.lesson_id;
      if (!body.due_date) delete body.due_date;
      await mutate(`/courses/${encodeURIComponent(state.courseId)}/assignments`, 'POST', body, 'Official assignment created.');
    });
    create.append(createForm.form); grid.append(create);
    const list = card('Assignments and grading', 'Inspect submissions, enter feedback, then choose whether to publish each grade.');
    appendItems(list, assignments(), 'No assignments yet', 'Create an assignment above to begin.', assignment => {
      const li = assignmentRow(assignment, 'teacher');
      const inspect = make('button', { className: 'button button-quiet button-small', text: 'Review submissions', attrs: { type: 'button' } });
      const details = make('div', { attrs: { hidden: '' } });
      inspect.addEventListener('click', async () => {
        if (!details.hidden) { details.hidden = true; inspect.textContent = 'Review submissions'; return; }
        inspect.disabled = true; inspect.textContent = 'Loading…';
        try { const result = await api(`/assignments/${encodeURIComponent(assignment.id)}`); renderSubmissions(details, result, assignment, true); details.hidden = false; inspect.textContent = 'Hide submissions'; }
        catch (error) { setNotice(error.message, true); inspect.textContent = 'Review submissions'; }
        finally { inspect.disabled = false; }
      });
      li.append(inspect, details); return li;
    });
    grid.append(list); content.append(grid);
  }
  function renderSubmissions(container, result, assignment, canGrade) {
    container.replaceChildren();
    const submissions = rows(result.submissions);
    if (!submissions.length) { container.append(empty('No submissions yet', 'A student submission will appear here when it is received.')); return; }
    for (const submission of submissions) {
      const item = make('article', { className: 'card' });
      item.append(text('h3', displayName(submission.student || { display_name: submission.display_name || submission.student_name }) + ' · submission'));
      item.append(text('p', submission.content || '', 'content-block'));
      if (submission.published && finite(submission.points)) item.append(text('p', `Published grade: ${submission.points}/${assignment.max_points}${submission.feedback ? ` · ${submission.feedback}` : ''}`));
      if (canGrade) {
        const grade = formFor('Grade this work', [
          { name: 'points', label: `Points (up to ${assignment.max_points})`, options: { required: true, type: 'number', min: 0, max: Number(assignment.max_points), step: 'any', value: finite(submission.points) ? submission.points : '' } },
          { name: 'feedback', label: 'Feedback for the learner', options: { type: 'textarea', maxLength: 3000, value: submission.feedback || '' } },
          { name: 'published', label: 'Publish grade', options: { choices: [{ value: 'false', label: 'Save as unpublished' }, { value: 'true', label: 'Publish to learner and parent' }], value: submission.published ? 'true' : 'false' } },
        ], 'Save grade', async values => {
          const points = Number(values.points);
          if (!Number.isFinite(points) || points < 0 || points > Number(assignment.max_points)) throw new Error(`Points must be between 0 and ${assignment.max_points}.`);
          await mutate(`/submissions/${encodeURIComponent(submission.id)}/grade`, 'POST', { points, feedback: values.feedback, published: values.published === 'true' }, values.published === 'true' ? 'Grade published.' : 'Grade saved as unpublished.');
        }, 'grade-form');
        item.append(grade.form);
      }
      container.append(item);
    }
  }

  function renderPeople() {
    const grid = sectionGrid();
    if (!state.user.is_admin) { grid.append(empty('Administrator access required', 'Only teacher administrators can create accounts and parent links.')); content.append(grid); return; }
    const users = state.users;
    const create = card('Create account', 'Provision a school account with a role and initial password.');
    const createForm = formFor('New user', [
      { name: 'username', label: 'Username', options: { required: true, maxLength: 64 } },
      { name: 'display_name', label: 'Display name', options: { required: true, maxLength: 120 } },
      { name: 'role', label: 'Role', options: { required: true, choices: ['teacher', 'student', 'parent', 'tutor'].map(value => ({ value, label: labelRole(value) })) } },
      { name: 'password', label: 'Initial password', options: { required: true, type: 'password', minLength: 12, maxLength: 256 } },
    ], 'Create account', async values => {
      await mutate('/users', 'POST', values, 'Account created.');
    });
    create.append(createForm.form); grid.append(create);
    const link = card('Link a parent and child', 'A parent can view only the published grades and progress for linked children.');
    const parents = users.filter(user => user.role === 'parent'), students = users.filter(user => user.role === 'student');
    if (parents.length && students.length) {
      const linkForm = formFor('Parent link', [
        { name: 'parent_id', label: 'Parent account', options: { required: true, choices: labelOptions(parents) } },
        { name: 'student_id', label: 'Student account', options: { required: true, choices: labelOptions(students) } },
      ], 'Create parent link', values => mutate('/parent-links', 'POST', values, 'Parent link created.'));
      link.append(linkForm.form);
    } else link.append(empty('Accounts needed', 'Create at least one parent and one student account first.'));
    grid.append(link);
    const directory = card('School accounts', 'Accounts currently available to this administrator.');
    appendItems(directory, users, 'No accounts yet', 'Create accounts as your school onboards learners and staff.', user => {
      const li = make('li', { className: 'list-row' });
      li.append(text('strong', displayName(user)), make('div', { className: 'meta' }, [make('span', { className: 'tag', text: labelRole(user.role) }), make('span', { text: user.username || '' })]));
      return li;
    });
    grid.append(directory); content.append(grid);
  }

  function renderStudentLearning() {
    const grid = sectionGrid(); coursePicker(grid);
    const course = courseData();
    if (!course) { content.append(grid); return; }
    const lessonCard = card(`Lessons · ${courseName(course)}`, 'Read a lesson, then open related assignment instructions when you are ready.');
    appendItems(lessonCard, lessons(), 'No lessons available', 'Your teacher has not added lessons to this course yet.', lessonRow);
    grid.append(lessonCard);
    const work = card('Assignments', 'Submit your work when it is ready. Once graded, your teacher may publish feedback here.');
    appendItems(work, assignments(), 'No assignments available', 'Your teacher will add course work here.', assignment => {
      const li = assignmentRow(assignment, 'student');
      const submit = make('button', { className: 'button button-secondary button-small', text: assignment.submitted ? 'View submission' : 'Submit work', attrs: { type: 'button' } });
      const editor = make('div', { attrs: { hidden: '' } });
      submit.addEventListener('click', async () => {
        editor.hidden = !editor.hidden; if (editor.childElementCount) return;
        const pane = card(assignment.submitted ? 'Your submission' : 'Submit work');
        if (assignment.submitted) {
          pane.append(empty('Loading your submission', 'Opening the work you sent to your teacher…'));
          try {
            const result = await api(`/assignments/${encodeURIComponent(assignment.id)}`);
            pane.replaceChildren(text('h3', 'Your response'));
            const ownSubmission = rows(result.submissions)[0];
            if (ownSubmission?.content) pane.append(text('p', ownSubmission.content, 'content-block'));
            else pane.append(empty('Submission unavailable', 'Your submission could not be displayed.'));
            if (ownSubmission?.published && finite(ownSubmission.points)) {
              pane.append(text('p', `Published grade: ${ownSubmission.points}/${assignment.max_points}`));
              if (ownSubmission.feedback) pane.append(text('p', `Feedback: ${ownSubmission.feedback}`));
            } else pane.append(text('p', 'Your teacher has not published a grade yet.', 'muted'));
          } catch (error) { pane.replaceChildren(empty('Submission unavailable', error.message)); }
        } else {
          const form = formFor('Your response', [{ name: 'content', label: 'Work', options: { type: 'textarea', required: true, maxLength: 12000 } }], 'Submit assignment', async values => {
            await mutate(`/assignments/${encodeURIComponent(assignment.id)}/submissions`, 'POST', values, 'Work submitted. Grading is not shared until your teacher publishes it.');
          }); pane.append(form.form);
        }
        editor.append(pane);
      });
      li.append(submit, editor); return li;
    });
    grid.append(work);
    const chat = card('Ask a question', 'Choose a lesson or assignment so the tutor can answer from course material.');
    if (!lessons().length && !assignments().length) chat.append(empty('Course material needed', 'Ask your teacher to add a lesson or assignment first.'));
    else {
      const contexts = [...lessons().map(lesson => ({ value: `lesson:${lesson.id}`, label: `Lesson · ${lesson.title}` })), ...assignments().map(item => ({ value: `assignment:${item.id}`, label: `Assignment · ${item.title}` }))];
      const form = formFor('Course tutor', [
        { name: 'context_id', label: 'Use this course material', options: { required: true, choices: contexts } },
        { name: 'question', label: 'Your question', options: { type: 'textarea', required: true, maxLength: 3000, placeholder: 'What would you like help understanding?' } },
      ], 'Ask tutor', async values => {
        const [kind, id] = values.context_id.split(':');
        const payload = { course_id: course.id, question: values.question, [kind === 'lesson' ? 'lesson_id' : 'assignment_id']: id };
        const submit = form.form.querySelector('button[type="submit"]'); submit.disabled = true; setNotice('Thinking…');
        try { const result = await api('/tutor-chat', { method: 'POST', body: payload });
          const answer = make('div', { className: 'content-block', attrs: { role: 'status', 'aria-live': 'polite' } }); answer.textContent = asText(result.answer) || 'No answer was returned.';
          form.form.append(text('h3', 'Tutor response', 'subsection'), answer);
          const citations = rows(result.citations);
          if (citations.length) { const list = make('ul', { className: 'citation-list' }); for (const citation of citations) list.append(text('li', isObj(citation) ? [citation.title, citation.text || citation.quote].filter(Boolean).join(' · ') || `Source ${citation.id || ''}` : citation)); form.form.append(list); }
          if (result.warning) form.form.append(text('p', result.warning, 'muted'));
          setNotice('Tutor response ready.');
        } catch (error) { setNotice(error.message, true); }
        finally { submit.disabled = false; }
      });
      chat.append(form.form);
    }
    grid.append(chat); content.append(grid);
  }

  function renderPreference() {
    const pane = card('Study preference', 'Choose how explanations are presented. This preference can be changed at any time.');
    const choices = [
      ['balanced', 'Balanced'], ['step_by_step', 'Step by step'], ['worked_examples', 'Worked examples'], ['visual', 'Visual explanations'], ['practice', 'Practice first'],
    ].map(([value, label]) => ({ value, label }));
    const form = formFor('Preferred approach', [{ name: 'learning_preference', label: 'Presentation preference', options: { required: true, choices, value: state.user.learning_preference || 'balanced' } }], 'Save preference', async values => {
      const ok = await mutate('/profile', 'POST', values, 'Study preference saved.');
      if (ok) { state.user.learning_preference = values.learning_preference; renderCurrent(); }
    });
    pane.append(form.form); content.append(pane);
  }

  function renderProgressReport(report, title) {
    const section = make('section', { className: 'card span-12' });
    section.append(text('h2', title));
    const official = isObj(report?.official) ? report.official : {};
    const practice = isObj(report?.practice) ? report.practice : {};
    const metrics = make('div', { className: 'two-column' });
    metrics.append(metricCard('Official course work', formatPercent(official.percent), `${official.earned ?? 0} of ${official.possible ?? 0} published points · ${official.graded_count ?? 0} graded assignments`));
    metrics.append(metricCard('Practice', formatPercent(practice.percent), `${practice.earned ?? 0} of ${practice.possible ?? 0} published points · ${practice.graded_count ?? 0} graded tasks`));
    section.append(metrics);
    const pending = Number(report?.pending_count || 0), missing = Number(report?.missing_count || 0);
    section.append(text('p', `${pending} without a published grade · ${missing} overdue and unsubmitted`, 'muted'));
    section.append(text('p', 'Topic status uses published official grades only: excelling is 85% or higher, needs attention is below 65%, and developing is between those thresholds. No status is a fixed prediction of ability.', 'fine-print'));
    const topics = rows(report?.topics);
    if (topics.length) {
      section.append(text('h3', 'Topic progress', 'subsection'));
      for (const topic of topics) {
        const line = make('div', { className: 'progress-line' });
        const status = typeof topic.status === 'string' ? topic.status.replaceAll('_', ' ') : 'no status';
        line.append(make('div', {}, [text('strong', topic.topic || 'Topic'), text('span', `${formatPercent(topic.percent)} · ${topic.graded_count || 0} graded · ${status}`)]));
        const track = make('div', { className: 'progress-track', attrs: { role: 'img', 'aria-label': `${topic.topic || 'Topic'}: ${formatPercent(topic.percent)}` } });
        const fill = make('div', { className: 'progress-fill' }); fill.style.width = `${finite(topic.percent) ? Math.max(0, Math.min(100, Number(topic.percent))) : 0}%`; track.append(fill); line.append(track); section.append(line);
      }
    } else section.append(empty('No topic evidence yet', 'Published official grades will provide a topic view over time.'));
    const published = rows(report?.records).filter(record => record.kind === 'official' && record.published && finite(record.points));
    section.append(text('h3', 'Published official grades', 'subsection'));
    appendItems(section, published, 'No published grades yet', 'Official grades appear here after a teacher publishes them.', record => {
      const row = make('li', { className: 'list-row' });
      row.append(text('strong', record.title || 'Course assignment'));
      const meta = make('div', { className: 'meta' });
      if (record.course_title) meta.append(make('span', { className: 'tag', text: record.course_title }));
      if (record.topic) meta.append(make('span', { className: 'tag', text: record.topic }));
      meta.append(make('span', { className: 'tag', text: `${record.points}/${record.max_points} points` }));
      row.append(meta);
      if (record.feedback) row.append(text('p', record.feedback));
      return row;
    });
    return section;
  }
  function renderProgressPicker(children) {
    const wrapper = make('div', { className: 'grid' });
    const select = make('section', { className: 'card span-12' });
    const picker = selectField(select, 'child', 'Linked child', labelOptions(children), state.childId || children[0]?.id);
    state.childId = String(picker.value || '');
    const reportHost = make('div', { className: 'grid span-12' });
    const load = async () => {
      state.childId = picker.value; reportHost.replaceChildren();
      if (!state.childId) return;
      reportHost.append(empty('Loading progress', 'Fetching the published progress report…'));
      try { const report = await api(`/students/${encodeURIComponent(state.childId)}/progress`); reportHost.replaceChildren(renderProgressReport(report, `Progress · ${displayName(children.find(child => String(child.id) === state.childId))}`)); }
      catch (error) { reportHost.replaceChildren(empty('Progress unavailable', error.message)); }
    };
    picker.addEventListener('change', load); select.append(reportHost); wrapper.append(select); load(); return wrapper;
  }
  function renderChildren() {
    const children = rows(state.dashboard.students);
    if (!children.length) { content.append(empty('No linked children', 'A teacher administrator can connect your parent account with a student account.')); return; }
    const wrapper = renderProgressPicker(children); content.append(wrapper);
  }
  function renderTutorLearners() {
    const students = rows(state.dashboard.students), grid = sectionGrid();
    appendItems(grid, students, 'No assigned learners', 'A teacher must assign you to a learner in a course before their progress is visible.', student => {
      const row = make('li', { className: 'list-row' });
      row.append(text('strong', displayName(student)), make('div', { className: 'meta' }, [make('span', { className: 'tag', text: student.learning_preference ? `Prefers ${student.learning_preference.replaceAll('_', ' ')}` : 'No preference selected' })]));
      const button = make('button', { className: 'button button-secondary button-small', text: 'View learning needs', attrs: { type: 'button' } });
      const reportBox = make('div', { attrs: { hidden: '' } });
      button.addEventListener('click', async () => {
        reportBox.hidden = !reportBox.hidden;
        if (reportBox.childElementCount) return;
        try { const report = await api(`/students/${encodeURIComponent(student.id)}/progress`); reportBox.append(renderProgressReport(report, `Published progress · ${displayName(student)}`)); }
        catch (error) { reportBox.append(empty('Progress unavailable', error.message)); }
      });
      row.append(button, reportBox); return row;
    });
    content.append(grid);
  }

  function renderPracticeEditor(draft, studentId, topic, draftCard) {
    const editorCourseId = String(state.courseId);
    let practiceLessonId = null;
    const requestedTopic = topic || draft.topic;
    draftCard.replaceChildren(
      text('h2', 'Review practice draft'),
      text('p', 'Edit any field. Nothing is shared with the learner until you publish the lesson and assignment.', 'muted'),
    );
    const edit = formFor('Editable draft', [
      { name: 'title', label: 'Lesson title', options: { required: true, maxLength: 140, value: draft.title || `Practice · ${requestedTopic}` } },
      { name: 'topic', label: 'Topic', options: { required: true, maxLength: 100, value: draft.topic || requestedTopic } },
      { name: 'learning_objectives', label: 'Learning objectives', options: { type: 'textarea', maxLength: 1600, value: draft.learning_objectives || '' } },
      { name: 'lesson_content', label: 'Lesson content', options: { type: 'textarea', required: true, maxLength: 10000, value: draft.lesson_content || '' } },
      { name: 'assignment_title', label: 'Practice assignment title', options: { required: true, maxLength: 140, value: draft.assignment_title || `Practice · ${requestedTopic}` } },
      { name: 'instructions', label: 'Practice instructions', options: { type: 'textarea', required: true, maxLength: 5000, value: draft.instructions || '' } },
    ], 'Publish lesson and practice assignment', async review => {
      setNotice('Publishing reviewed practice…');
      try {
        if (!practiceLessonId) {
          const lessonResult = await api(`/courses/${encodeURIComponent(editorCourseId)}/lessons`, { method: 'POST', body: { title: review.title, content: review.lesson_content, learning_objectives: review.learning_objectives, topic: review.topic, target_student_id: studentId } });
          const lesson = lessonResult.lesson || lessonResult;
          practiceLessonId = lesson.id;
        }
        await api(`/courses/${encodeURIComponent(editorCourseId)}/assignments`, { method: 'POST', body: { title: review.assignment_title, instructions: review.instructions, lesson_id: practiceLessonId, topic: review.topic, max_points: 10, target_student_id: studentId, kind: 'practice' } });
        state.draft = null; await refreshDashboard(); setNotice('Targeted lesson and practice assignment published.'); renderCurrent();
      } catch (error) {
        if (practiceLessonId) {
          for (const key of ['title', 'topic', 'learning_objectives', 'lesson_content']) edit.controls[key].disabled = true;
          edit.form.querySelector('button[type="submit"]').textContent = 'Retry assignment';
          edit.form.prepend(text('p', 'The lesson was published, but the practice assignment was not saved. The lesson fields are locked to prevent a duplicate. Review the assignment details and retry.', 'notice error'));
        }
        setNotice(error.message || 'Could not publish practice.', true);
      }
    });
    draftCard.append(edit.form);
  }

  function renderPractice() {
    const grid = sectionGrid(); coursePicker(grid);
    const course = courseData();
    if (!course) { content.append(grid); return; }
    const students = rows(state.dashboard.students).filter(person => studentsInCourse().some(item => String(item.id) === String(person.id)) || !state.detail?.students);
    const draftCard = card('Prepare targeted practice', 'Generate an editable draft from this course and learner’s authorized progress, then review and publish it yourself.');
    if (!students.length) draftCard.append(empty('No assigned learners in this course', 'Choose a course where a teacher has assigned you to support a learner.'));
    else {
      const draftForm = formFor('Practice request', [
        { name: 'student_id', label: 'Assigned learner', options: { required: true, choices: labelOptions(students), value: state.learnerId } },
        { name: 'topic', label: 'Topic to practise', options: { required: true, maxLength: 100 } },
        { name: 'request', label: 'What would make this practice useful?', options: { type: 'textarea', maxLength: 1600, placeholder: 'For example: add a short worked example before the questions.' } },
      ], 'Generate editable AI draft', async values => {
        state.learnerId = values.student_id; setNotice('Preparing a practice draft…');
        try { state.draft = await api('/practice-drafts', { method: 'POST', body: { course_id: course.id, student_id: values.student_id, topic: values.topic, request: values.request } });
          renderPracticeEditor(state.draft, values.student_id, values.topic, draftCard); setNotice('Draft ready for your review.');
        } catch (error) { setNotice(error.message, true); }
      });
      draftCard.append(draftForm.form);
      draftCard.append(text('p', 'If AI drafting is unavailable, start with a blank lesson and assignment instead.', 'muted'));
      const manual = make('button', { className: 'button button-secondary', text: 'Start a manual draft', attrs: { type: 'button' } });
      manual.addEventListener('click', () => {
        if (!draftForm.form.reportValidity()) return;
        const studentId = draftForm.controls.student_id.value;
        const topic = draftForm.controls.topic.value.trim();
        state.learnerId = studentId;
        state.draft = { title: '', instructions: '', lesson_content: '', learning_objectives: '', topic };
        renderPracticeEditor(state.draft, studentId, topic, draftCard);
        setNotice('Blank draft ready. Add lesson content and instructions before publishing.');
      });
      draftCard.append(manual);
    }
    grid.append(draftCard);
    const work = card('Practice in this course', 'Practice grades support learning and do not change official course averages.');
    appendItems(work, assignments().filter(item => item.kind === 'practice'), 'No practice tasks yet', 'Create targeted practice when a learner is ready for more work.', item => assignmentRow(item, 'tutor'));
    grid.append(work); content.append(grid);
  }

  async function bootstrap() {
    $('#login-form').addEventListener('submit', async event => {
      event.preventDefault();
      const form = event.currentTarget;
      if (!form.reportValidity()) return;
      const button = form.querySelector('button[type="submit"]'); button.disabled = true; setLoginMessage('Signing in…');
      try {
        const data = await api('/auth/login', { method: 'POST', auth: false, body: { username: $('#login-username').value.trim(), password: $('#login-password').value } });
        if (!isObj(data.user) || !['teacher', 'student', 'parent', 'tutor'].includes(data.user.role)) throw new Error('This account is not configured for the learning workspace.');
        await showWorkspace(data.user, data.csrf_token);
      } catch (error) { setLoginMessage(error.message || 'Sign-in failed.'); }
      finally { button.disabled = false; }
    });
    $('#logout-button').addEventListener('click', async () => {
      try { await api('/auth/logout', { method: 'POST', body: {} }); } catch { /* A timed-out session is already signed out. */ }
      showLogin('You have signed out.');
    });
    try {
      const data = await api('/auth/me', { auth: false });
      if (isObj(data.user) && ['teacher', 'student', 'parent', 'tutor'].includes(data.user.role)) await showWorkspace(data.user, data.csrf_token);
      else showLogin();
    } catch { showLogin(); }
    if (document.body.dataset.focusLogin === 'true') setTimeout(() => $('#login-username').focus({ preventScroll: true }), 0);
  }

  bootstrap();
})();
