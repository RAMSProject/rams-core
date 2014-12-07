// Regular person registration.js

// Load and instantiate Chance
// default random generator doesn't work in Casper, so replace it
var chance = require('./import_chance.js').Chance(Math.random);
var clientutils = require('clientutils');

// first we generate our test info
myAttendeeInfo = {
  'first_name'         : chance.first(),
  'last_name'          : chance.last(),
  'email'              : chance.email(),
  'badge_printed_name' : chance.name(),
  'cellphone'          : chance.phone(),
  'ec_name'            : chance.name(),
  'ec_phone'           : chance.phone(),
  'found_how'          : chance.word(),
  'comments'           : chance.sentence(),
  'address1'           : chance.address(),
  'address2'           : chance.sentence({words: 2}),
  'city'               : chance.city(),
  'region'             : chance.state(),
  'zip_code'           : chance.zip(),
  'country'            : 'United States',
}

casper.test.begin('Adding a regular registration to the cart is successful', 6, function suite(test) {
    casper.start('http://localhost:8282/magfest/preregistration/form', function() {
        //this.echo(this.getCurrentUrl());
        test.assertTitle("MAGFest - Preregistration", "preregistration title is as expected");
        test.assertExists('form[action="form"]', "main form is found");
        this.fill('form[action="form"]', myAttendeeInfo, false);
        //these 3 type in the birthdate
        //FIXME: XPath here is fragile, find a better selector to use
        this.sendKeys({type: 'xpath', path: '//*[@id="mainContainer"]/div[3]/form/div[15]/div/span/span[1]/input[1]'},'1');
        this.sendKeys({type: 'xpath', path: '//*[@id="mainContainer"]/div[3]/form/div[15]/div/span/span[1]/input[2]'},'1');
        this.sendKeys({type: 'xpath', path: '//*[@id="mainContainer"]/div[3]/form/div[15]/div/span/span[1]/input[3]'},'1990');
        //FIXME: we don't currently test the autocomplete of addresses
        //casper.evaluate(function() {
        //  __utils__.echo(JSON.stringify(__utils__.getFormValues('form[action="form"]')), null, 4);
        //});
        this.click('button[value=Preregister]');
    });
    casper.waitForUrl(/index$/, function() {
        //this.echo(this.getCurrentUrl());
        test.assertUrlMatch(/index$/, 'shopping cart displayed');
        test.assertExists('.stripe-button-el','stripe button present');
        test.assertSelectorHasText('.footable-visible', myAttendeeInfo.first_name + ' ' + myAttendeeInfo.last_name, 'Name matches')
        test.assertSelectorHasText('.footable-visible', '$60', 'Price is correct');
        this.click('button.stripe-button-el');
        this.echo(this.getCurrentUrl());
    });
    casper.withFrame('stripe_checkout_app', function() {
      this.echo(this.getCurrentUrl());
      test.assertTitle("Stripe Checkout", "Stripe Checkout popup loaded");
      //FIXME: this whole section is a mess. It works if I use JCB, because that has no zip code check. ugh.
      casper.waitUntilVisible('#card_number', function() {
          this.fillXPath('form', {
            '//*[@id="card_number"]' : '3530111333300000',
            '//*[@id="cc-exp"]'      : '01 / 20',
            '//*[@id="cc-csc"]'      : '234',
          });
          //test.assertExists('#card_number', "Card Number field is visible");
          //this.sendKeys({type: 'xpath', path: '//*[@id="card_number"]'},'3530 1113 3330 0000');
      //});
      //casper.waitUntilVisible('#cc-exp', function() {
        //test.assertExists('#cc-exp', "Expiration Date field is visible");
        //this.sendKeys({type: 'xpath', path: '//*[@id="cc-exp"]'},'0120');
      //});
      //casper.waitUntilVisible('#cc-csc', function() {
        //test.assertExists('#cc-csc', "CSC field is visible");
      //  this.sendKeys({type: 'xpath', path: '//*[@id="cc-csc"]'},'234');
      this.echo(this.getHTML());
        casper.evaluate(function() {
          __utils__.echo(JSON.stringify(__utils__.getFormValues('form')), null, 4);
        });
        this.evaluate(function() {
          $("#card_number").val('3530111333300000');
          $("#cc-exp").val('01 / 20');
          $("#cc-csc").val('999');
          $('#submitButton').click();
    
          $('form input').each(function(index) {
            __utils__.echo($(this).attr('name') + " = " + $(this).val());
          });
        });
        //this.waitUntilVisible('#submitButton > .spinnerContainer', function() {
        //  this.echo('gotit');
        //});
      });
      //casper.waitUntilVisible('#billing-zip', function() {
      //  test.assertExists('#billing-zip', "Zip Code field is visible");
      //  this.sendKeys({type: 'xpath', path: '//*[@id="billing-zip"]'},'12345', {keepFocus: true});
      //});
      //FIXME: probably should test more fields in the Stripe dialog are correct
    });
    casper.waitForUrl(/paid_preregistrations/, function() {
      this.echo(this.getCurrentUrl());
      test.assertUrlMatch(/paid_preregistrations/, 'Confirmation Screen Displayed');
      test.assertExists('.stripe-button-el','stripe button present');
      test.assertSelectorHasText('td', myAttendeeInfo.first_name + ' ' + myAttendeeInfo.last_name, 'Name matches')
      test.assertSelectorHasText('td', myAttendeeInfo.badge_printed_name, 'Badge Name matches');
      //FIXME: Add test of confirm link
      },function(){
        this.die('Failed to load confirm screen, URL is: ' + this.getCurrentUrl())
      }, 5000);
    casper.run(function() {
        test.done();
    });
});
