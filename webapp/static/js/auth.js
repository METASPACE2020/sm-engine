function backendSignIn(id_token) {
    $.ajax({
        url: '/auth',
        type: 'POST',
        contentType: 'application/x-www-form-urlencoded',
        data: {'id_token': id_token, 'action': 'sign_in'}
    }).done(function() {
        console.log('Sent a sign in request to the backend');
    }).error(function(error) {
        console.log(error);
    });
}

function renderSignInButton() {
    gapi.signin2.render('google-sign-in', {
        'scope': 'profile email',
        'width': 200,
        'height': 35,
        'longtitle': true,
        'theme': 'dark',
        'onsuccess': function(googleUser) {
            console.log('Signed in as: ' + googleUser.getBasicProfile().getName());
            backendSignIn(googleUser.getAuthResponse().id_token);
        },
        'onfailure': function (error) {
            console.log(error);
        }
    });
}

function backendSignOut() {
    $.ajax({
        url: '/auth',
        type: 'POST',
        contentType: 'application/x-www-form-urlencoded',
        data: {'action': 'sign_out'}
    }).done(function() {
        console.log('Sent a sign out request to the backend');
    }).error(function() {
        console.log('Error');
    });
}

function addSignOutAction() {
    $('#google-sign-out').click(function() {
        var auth2 = gapi.auth2.getAuthInstance();
        auth2.disconnect().then(function () {
            console.log('Signed out');
        });
        backendSignOut();
    });
}
