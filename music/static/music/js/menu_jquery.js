$(document).ready(function () {
    $('#cssmenu > ul > li > a').click(function () {
        $('#cssmenu li').removeClass('active');
        $(this).closest('li').addClass('active');
        var checkElement = $(this).next();
        if ((checkElement.is('ul')) && (checkElement.is(':visible'))) {
            $(this).closest('li').removeClass('active');
            checkElement.slideUp('normal');
        }
        if ((checkElement.is('ul')) && (!checkElement.is(':visible'))) {
            $('#cssmenu ul ul:visible').slideUp('normal');
            checkElement.slideDown('normal');
        }
        if ($(this).closest('li').find('ul').children().length == 0) {
            return true;
        } else {
            return false;
        }
    });
});


// Login Form
// Login Form Dropdown
$(function () {
    var button = $('#loginContainer #userAvatarButton');
    var box = $('#loginContainer #loginBox');
    var form = $('#loginContainer #loginForm');

    if (button.length > 0 && box.length > 0) {
        button.removeAttr('href');
        button.mouseup(function (login) {
            box.toggle();
            button.toggleClass('active');
        });
        form.mouseup(function () {
            return false;
        });
        $(document).mouseup(function (login) {
            if ($(login.target).closest('#userAvatarButton').length === 0) {
                button.removeClass('active');
                box.hide();
            }
        });
    }
});