from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from .models import Course, Enrollment, Question, Choice, Submission
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)


# User Registration
def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = False

        try:
            User.objects.get(username=username)
            user_exist = True
        except User.DoesNotExist:
            logger.info("New user registration")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )

            login(request, user)
            return redirect('onlinecourse:index')

        else:
            context['message'] = "User already exists."

            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )


# User Login
def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        else:
            context['message'] = "Invalid username or password."

            return render(
                request,
                'onlinecourse/user_login_bootstrap.html',
                context
            )

    else:
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context
        )


# User Logout
def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


# Check Whether the User Is Enrolled
def check_if_enrolled(user, course):
    is_enrolled = False

    if user.id is not None:
        num_results = Enrollment.objects.filter(
            user=user,
            course=course
        ).count()

        if num_results > 0:
            is_enrolled = True

    return is_enrolled


# Course List View
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user

        courses = Course.objects.order_by(
            '-total_enrollment'
        )[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(
                    user,
                    course
                )

        return courses


# Course Detail View
class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


# Enroll in a Course
def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)

    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse(
            viewname='onlinecourse:course_details',
            args=(course.id,)
        )
    )


# Extract Selected Answers from the Exam Form
def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            value = request.POST[key]

            try:
                choice_id = int(value)
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


# Submit Exam
def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    if request.method != 'POST':
        return redirect(
            'onlinecourse:course_details',
            course_id=course_id
        )

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    selected_answers = extract_answers(request)

    for choice_id in selected_answers:
        choice = get_object_or_404(
            Choice,
            pk=choice_id
        )

        # Ensure the selected choice belongs to this course.
        if choice.question.lesson.course_id == course.id:
            submission.choices.add(choice)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


# Show Exam Results
def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(
        Course,
        pk=course_id
    )

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__user=request.user,
        enrollment__course=course
    )

    questions = Question.objects.filter(
        lesson__course=course
    ).order_by('id')

    selected_choices = submission.choices.all()

    total_score = 0
    possible_score = 0
    question_results = []

    for question in questions:
        # Maximum marks available for this question.
        possible_score += question.grade

        selected_for_question = selected_choices.filter(
            question=question
        )

        correct_choices = question.choice_set.filter(
            is_correct=True
        )

        selected_correct = selected_for_question.filter(
            is_correct=True
        ).count()

        selected_incorrect = selected_for_question.filter(
            is_correct=False
        ).count()

        is_correct = (
            correct_choices.exists()
            and selected_correct == correct_choices.count()
            and selected_incorrect == 0
        )

        # Award marks only when the answer is completely correct.
        question_score = question.grade if is_correct else 0
        total_score += question_score

        question_results.append({
            'question': question,
            'selected_choices': selected_for_question,
            'correct_choices': correct_choices,
            'is_correct': is_correct,
            'question_score': question_score,
        })

    # Calculate the grade percentage.
    if possible_score > 0:
        grade = (total_score / possible_score) * 100
    else:
        grade = 0

    context = {
        'course': course,
        'submission': submission,
        'question_results': question_results,
        'total_score': total_score,
        'possible_score': possible_score,
        'score': total_score,
        'grade': grade,
        'total_questions': questions.count(),
        'passed': possible_score > 0 and total_score > 0,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
