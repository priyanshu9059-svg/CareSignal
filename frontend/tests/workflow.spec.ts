import {test,expect} from '@playwright/test';
test('participant to officer support workflow',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await page.getByRole('button',{name:'victim',exact:true}).click();
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('button',{name:'Consent & privacy',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Consent & privacy',exact:true}).click();
 await page.getByLabel('I agree to optional wellbeing analysis').check();
 await page.getByLabel('I also agree to optional voice processing').check();
 await page.getByRole('button',{name:'Save preferences'}).click();
 await page.getByRole('button',{name:'Start check-in',exact:true}).first().click();
 for(const label of ['1. How have you been feeling recently?','2. How often have you felt anxious or afraid?','3. How difficult has sleeping been?','4. How difficult are daily activities?','5. Have you avoided people or places because of fear?','6. Have legal proceedings increased your stress?'])await page.getByRole('combobox',{name:label,exact:true}).selectOption('4');
 await page.getByRole('combobox',{name:'7. Are you facing threats or intimidation?',exact:true}).selectOption('true');
 await page.getByRole('combobox',{name:'8. Do you feel safe at present?',exact:true}).selectOption('false');
 await page.getByRole('button',{name:'Record voice',exact:true}).click();
 await expect(page.getByRole('button',{name:'Stop recording',exact:true})).toBeVisible();
 await page.waitForTimeout(1400);
 await page.getByRole('button',{name:'Stop recording',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Recording processed', {timeout:15000});
 await page.getByLabel('Would you like to tell us anything in your own words?',{exact:true}).fill('Mujhe bahut darr lag raha hai. Mere bhai ko dhamki di. Court jaane se dar lag raha hai. Neend nahi aati.');
 await page.getByRole('button',{name:'Send check-in',exact:true}).click();
 await expect(page.getByText('Your check-in has been received.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await page.getByRole('button',{name:'officer',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'A clearer view. Earlier support.'})).toBeVisible();
 await page.getByRole('button',{name:'Alerts & review',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Alerts & escalation'})).toBeVisible();
 await page.getByRole('button',{name:'Review case',exact:true}).first().click();
 await expect(page.getByRole('heading',{name:'What changed?',exact:true})).toBeVisible();
 await page.getByLabel('Internal notes',{exact:true}).fill('Browser workflow verification');
 await page.getByRole('button',{name:'Confirm intervention',exact:true}).click();
 await expect(page.locator('.toast')).toContainText('Saved successfully');
 await page.getByLabel('Follow-up date and time',{exact:true}).fill('2027-01-20T10:30');
 const followupResponse=page.waitForResponse(r=>r.url().endsWith('/api/follow-ups')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Schedule follow-up',exact:true}).click();
 expect((await followupResponse).status()).toBe(200);
 await expect(page.locator('.toast')).toContainText('Saved successfully');
 await page.screenshot({path:'test-results/case-review.png',fullPage:true});
 await page.getByRole('button',{name:'Sign out',exact:true}).click();
 await page.getByRole('button',{name:'victim',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByText('Jan 20, 2027',{exact:false}).first()).toBeVisible();
 await page.getByLabel('Demo mode').check();await page.getByRole('button',{name:'improvement',exact:true}).click();
 await expect(page.locator('.toast')).toContainText('Scenario saved');
 await page.getByRole('button',{name:'Sign out',exact:true}).click();
 for(const role of ['state','national','admin']){
  await page.getByRole('button',{name:role,exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByRole('heading',{name:'A clearer view. Earlier support.'})).toBeVisible();
  if(role==='admin'){await page.getByRole('button',{name:'Model research',exact:true}).click();await expect(page.getByRole('heading',{name:'Research & model monitoring'})).toBeVisible();}
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
 }
 expect(errors).toEqual([]);
});
test('mobile login and Hindi selection',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await page.getByLabel('Language').selectOption('hi');
 await page.getByRole('button',{name:'victim',exact:true}).click();await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await expect(page.getByRole('heading',{name:'आपकी भलाई मायने रखती है।'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

